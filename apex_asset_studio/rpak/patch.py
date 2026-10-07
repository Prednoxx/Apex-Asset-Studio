"""Bounded native patch reconstruction."""
import struct
from collections import Counter
from .oodle_stream import ScanCancelled


def decode_table(data,pos,bits):
    size = 1 << bits
    values, lengths = [None]*size, [0]*size
    code = 0; depth = None; filled = 0
    while filled < size:
        if pos >= len(data): raise ValueError('truncated patch Huffman table')
        byte = data[pos]; pos += 1
        new_depth = (byte & 7) + 1
        if new_depth > bits or (depth is not None and new_depth < depth):
            raise ValueError('invalid patch Huffman code length')
        if depth is not None: code = (code + 1) << (new_depth-depth)
        depth = new_depth
        if code >= 1 << depth: raise ValueError('oversubscribed patch Huffman table')
        reverse = int(f'{code:0{depth}b}'[::-1],2)
        for i in range(reverse,size,1<<depth):
            if values[i] is not None: raise ValueError('duplicate patch Huffman entry')
            values[i],lengths[i] = byte >> 3,depth
            filled += 1
    return values,lengths,pos


class Bits:
    def __init__(self,data,start,end): self.data,self.start,self.end,self.pos=data,start,end,0
    def peek(self,n):
        if n < 0 or self.pos+n > (len(self.data)-self.start)*8: raise ValueError('patch commands exceed buffer')
        at = self.start + self.pos//8; shift = self.pos & 7
        count = (shift+n+7)//8
        return (int.from_bytes(self.data[at:at+count],'little') >> shift) & ((1<<n)-1)
    def read(self,n):
        if self.pos+n > (self.end-self.start)*8: raise ValueError('patch commands exceed control stream')
        value = self.peek(n);self.pos += n;return value


class Chain:
    def __init__(self,parts): self.parts=parts;self.index=0;self.offset=0;self.consumed=0
    def take(self,count):
        if count < 0: raise ValueError('negative patch source extent')
        while count:
            if self.index >= len(self.parts): raise ValueError('patch source stream exhausted')
            data,start,end = self.parts[self.index]
            size = min(count,end-start-self.offset)
            if not size:
                self.index += 1;self.offset = 0;continue
            # Bound copy allocation size
            size = min(size,4*1024*1024)
            yield data[start+self.offset:start+self.offset+size]
            self.offset += size;self.consumed += size;count -= size
    def skip(self,count):
        for _ in self.take(count): pass


def reconstruct(archive,parents,path,stop=None):
    header,layout = archive.header,archive.layout
    if not header.patch_count: raise ValueError('archive has no edit stream')
    first = struct.unpack_from('<i',archive.data,header.header_size+4)[0]
    if first < 0 or first > len(archive.pages): raise ValueError('invalid first contained patch page')
    controls = archive.data[layout.patch_stream:layout.page_data]
    commands,cl,pos = decode_table(controls,0,6)
    exponents,el,pos = decode_table(controls,pos,8)
    if any(x > 6 for x in commands): raise ValueError('unsupported patch edit command')
    if pos+8 > len(controls): raise ValueError('truncated patch stream prologue')
    relative = int.from_bytes(controls[pos:pos+3],'little')
    replacement = pos+relative
    if replacement < pos+3 or replacement > len(controls): raise ValueError('invalid replacement stream offset')
    bits = Bits(controls,pos,replacement);bits.read(24)
    chain = Chain([(archive.data,layout.page_data,len(archive.data))]+[(p.data,p.header.header_size,len(p.data)) for p in parents])
    offsets=[];end=layout.page_data
    for page in archive.pages: offsets.append(end);end += page.size
    pages = list(range(first,len(archive.pages)))+list(range(first))
    page_cursor=0;page_remaining=0
    initial = sum(p.size for p in archive.pages[first:])
    stats=Counter();written=0
    with open(path,'wb') as out:
        out.write(archive.data[:layout.page_data]);out.truncate(end)
        def write(blob):
            nonlocal page_cursor,page_remaining,written
            at=0
            while at < len(blob):
                if not page_remaining:
                    if page_cursor >= len(pages): raise ValueError('patch edit output exceeds page table')
                    pi=pages[page_cursor];page_cursor += 1;page_remaining=archive.pages[pi].size
                    out.seek(offsets[pi])
                    if not page_remaining: continue
                size=min(page_remaining,len(blob)-at)
                out.write(blob[at:at+size]);page_remaining -= size;at += size;written += size
        if initial:
            for blob in chain.take(initial): write(blob)
        expected=sum(p.size for p in archive.pages)
        while written < expected:
            if stop and stop.is_set(): raise ScanCancelled()
            i=bits.peek(6);command=commands[i];bits.read(cl[i]);stats[command] += 1
            if command <= 3:
                i=bits.peek(8);e=exponents[i];bits.read(el[i])
                if e > 32: raise ValueError('patch run exponent too large')
                count=(1<<e)+bits.read(e)
            else: count={4:3,5:7,6:6}[command]
            if command == 1: chain.skip(count);continue
            if command in (4,5,6):
                edits=2 if command==6 else 1
                if replacement+edits > len(controls): raise ValueError('patch replacement stream exhausted')
                write(controls[replacement:replacement+edits]);replacement += edits;chain.skip(edits)
                for blob in chain.take(count): write(blob)
            elif command in (2,3):
                if replacement+count > len(controls): raise ValueError('patch replacement stream exhausted')
                write(controls[replacement:replacement+count]);replacement += count
                if command==3:chain.skip(count)
            else:
                for blob in chain.take(count):write(blob)
        if written != expected or page_remaining: raise ValueError('incomplete reconstructed page output')
    return {'page_bytes':written,'commands':dict(stats),'source_bytes_consumed':chain.consumed,
            'replacement_bytes_consumed':replacement,'control_bits_consumed':bits.pos,
            'parents':[str(p.path) for p in parents]}
