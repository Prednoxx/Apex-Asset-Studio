import struct
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from apex_asset_studio.rpak.oodle_stream import frame_stream,decompress_stream,ScanCancelled
from apex_asset_studio.rpak.guid import string_to_guid
from apex_asset_studio.rpak.patch import reconstruct,decode_table
from apex_asset_studio.rpak.starpak import StarPakIndex
from apex_asset_studio.rpak.settings import SettingsLayout,SettingsDecoder
from apex_asset_studio.rpak.model import unpack_normal,unpack_tangent,uv_channel_indices,simple_bone_influences


class NativeFormatTests(unittest.TestCase):
    def test_packed_bone_count_is_extra_influences_and_last_weight_is_implicit(self):
        self.assertEqual(simple_bone_influences(0,0,5), [(5,32767)])
        self.assertEqual(simple_bone_influences(8192,16000,(1<<24)|(9<<8)|5), [(5,8192),(9,24575)])
        self.assertEqual(simple_bone_influences(8192,8192,(2<<24)|(11<<16)|(9<<8)|5), [(5,8192),(9,8192),(11,16383)])
        with self.assertRaises(ValueError): simple_bone_influences(0,0,3<<24)
    def test_sparse_uv_flags_preserve_second_channel_after_empty_slot(self):
        self.assertEqual(uv_channel_indices((2 << 24) | (2 << 32)), [0, 2])
        self.assertEqual(uv_channel_indices(2 << 24), [0])
        with self.assertRaises(ValueError): uv_channel_indices((2 << 24) | (3 << 32))
    def test_restart_spans_strip_padding_and_decode_independently(self):
        a,b=b'A'*0x40000,b'BCD'
        stream=b'\xcc\x06'+a+b'\xcc\x06'+b+b'padding'
        spans=frame_stream(stream,len(a)+len(b))
        self.assertEqual([s.raw_size for s in spans],[len(a),len(b)])
        calls=[]
        def decode(data,size): calls.append(data);return data[2:]
        result=decompress_stream(stream,len(a)+len(b),SimpleNamespace(decompress=decode))
        self.assertEqual(result,a+b);self.assertEqual(len(calls),2)
        self.assertNotIn(b'padding',calls[-1])
        stop=Event();stop.set()
        with self.assertRaises(ScanCancelled):decompress_stream(stream,len(a)+len(b),SimpleNamespace(decompress=decode),stop)

    def test_truncated_oodle_fails_before_native_decoder(self):
        with self.assertRaises(ValueError):frame_stream(b'\xcc\x06short',100)

    def test_guid_normalization_matches_real_model_identifier(self):
        name='mdl/humans/class/light/pilot_light_wraith_legendary_02.rmdl'
        self.assertEqual(string_to_guid(name),0x6C4AD606544BF220)
        self.assertEqual(string_to_guid(name.upper().replace('/','\\')),string_to_guid(name))

    def test_dynamic_array_offset_is_relative_to_current_record(self):
        data=bytearray(64);struct.pack_into('<ii',data,16,2,12);struct.pack_into('<2i',data,28,41,42)
        child=SettingsLayout('child',4,0,[{'name':'value','kind':1,'offset':0,'child':0}],{})
        parent=SettingsLayout('parent',8,0,[{'name':'array','kind':9,'offset':0,'child':0}],{0:child})
        decoder=SettingsDecoder(SimpleNamespace(data=data))
        self.assertEqual(decoder.values(parent,16,64)['array'],[{'value':41},{'value':42}])
        struct.pack_into('<i',data,16,1000000)
        with self.assertRaises(ValueError):decoder.values(parent,16,64)

    def test_starpak_extent_cannot_bypass_footer_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stream.starpak';path.write_bytes(b'payload!'+struct.pack('<QQQ',0,8,1))
            index=StarPakIndex(path).parse();self.assertEqual(index.read(0),b'payload!')
            with self.assertRaises(ValueError):index.read(0,9)
            with self.assertRaises(KeyError):index.read(100,1)
            path.write_bytes(b'payload!'+struct.pack('<QQQ',0,100,1))
            with self.assertRaises(ValueError):StarPakIndex(path).parse()

    def test_patch_edits_cross_pages_without_relocating_page_indices(self):
        # Canonical Huffman tables: commands 0..6 with depths 1,2,3,4,5,6,6.
        commands=bytes((symbol<<3)|(depth-1) for symbol,depth in enumerate((1,2,3,4,5,6,6)))
        exponents=bytes((symbol<<3)|2 for symbol in range(8))
        bits=8;pos=24
        def append(value,n):
            nonlocal bits,pos
            bits |= value << pos;pos += n
        append(1,2);append(2,3);append(0,2) # skip four metadata bytes
        append(0,1);append(2,3);append(0,2) # copy four bytes
        append(15,5) # command 4: replace one byte, copy three
        controls=commands+exponents+bits.to_bytes(8,'little')+b'X'
        prefix=struct.pack('<ii',len(controls),2)
        archive=SimpleNamespace(header=SimpleNamespace(patch_count=1,header_size=0),
            layout=SimpleNamespace(patch_stream=8,page_data=8+len(controls)),data=prefix+controls,
            pages=[SimpleNamespace(size=4),SimpleNamespace(size=4)])
        parent=SimpleNamespace(data=b'header!!METAABCDEFGH',header=SimpleNamespace(header_size=8),path=Path('base.rpak'))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'patched'
            result=reconstruct(archive,[parent],target)
            self.assertEqual(target.read_bytes()[archive.layout.page_data:],b'ABCDXFGH')
            self.assertEqual(result['page_bytes'],8)
        with self.assertRaises(ValueError):decode_table(b'\xff',0,6)

    def test_tangent_unpack_preserves_handedness_and_orthogonality(self):
        value=(2<<29)|(256<<19)|(256<<10)|371|0x80000000
        normal=unpack_normal(value);tangent=unpack_tangent(value,normal)
        self.assertAlmostEqual(sum(a*b for a,b in zip(normal,tangent)),0,places=6)
        self.assertAlmostEqual(sum(v*v for v in tangent[:3]),1,places=6)
        self.assertEqual(tangent[3],-1)
