"""Compatible animation picker."""
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .preview import ModelPreview


def show_animation_picker(self):
    """Preview and confirm declared clips."""
    if not self._model or self._busy or self._scanning: return
    if self._animation_picker: self._animation_picker['window'].lift();return
    self._playing=False;self.play_btn.configure(text='Play')
    rows = self.catalog.declared_animations(self._model.guid,self._model.rig_guids)
    unique={}
    for row in rows: unique.setdefault(row['guid'],row)
    rows=list(unique.values())
    window = tk.Toplevel(self); window.title(f'Animations · {self.inspector_title.get()}')
    window.configure(background=self.tokens['background'])
    window.geometry('1180x700');window.minsize(950,550);window.transient(self);window.grab_set()
    if hasattr(self, '_icon_image'): window.iconphoto(False, self._icon_image)
    heading=ttk.Frame(window,padding=(16,14,16,0));heading.pack(fill='x')
    ttk.Label(heading,text='Animations',style='Title.TLabel').pack(side='left')
    ttk.Label(heading,text=f'{len(rows):,} sequences declared for {self.inspector_title.get()}',style='Muted.TLabel').pack(side='left',padx=(12,0),pady=(6,0))
    query = tk.StringVar(); entry=ttk.Entry(window,textvariable=query);entry.pack(fill='x',padx=16,pady=(12,10))
    self._placeholder(entry,query,'Filter sequences')
    body=ttk.Panedwindow(window,orient='horizontal');body.pack(fill='both',expand=True,padx=16,pady=(0,4))
    frame=ttk.Frame(body,style='Panel.TFrame');body.add(frame,weight=3)
    table=ttk.Treeview(frame,columns=('name','guid','link','source'),show='headings')
    for key,title,width in [('name','SEQUENCE',420),('guid','GUID',150),('link','LINK',130),('source','RPAK',280)]:
        table.heading(key,text=title,anchor='w');table.column(key,width=width,anchor='w')
    table.configure(displaycolumns=('name','source'));table.column('name',width=350);table.column('source',width=160)
    table.pack(side='left',fill='both',expand=True)
    scroll=ttk.Scrollbar(frame,command=table.yview);scroll.pack(side='right',fill='y');table.configure(yscrollcommand=scroll.set)
    def refresh(*_):
        table.delete(*table.get_children())
        text=query.get().casefold()
        for i,row in enumerate(rows):
            if text and text not in (str(row['name'])+' '+row['guid']+' '+row['filename']).casefold(): continue
            link='Model + rig' if row['declared_model_link'] and row['declared_rig_links'] else 'Model header' if row['declared_model_link'] else 'Rig header'
            name=Path(row['name'] or '').stem.replace('_',' ').strip().title()
            table.insert('','end',iid=str(i),values=(name,row['guid'],link,row['filename']))
    query_trace=query.trace_add('write',refresh);refresh();entry.focus_set()
    right=ttk.Frame(body,style='Panel.TFrame',padding=(14,14,14,10));body.add(right,weight=2)
    viewport_frame=ttk.Frame(right,style='Hairline.TFrame',padding=1);viewport_frame.pack(fill='both',expand=True)
    viewport=ModelPreview(viewport_frame);viewport.pack(fill='both',expand=True)
    viewport.set_palette(self.tokens['viewport']);viewport.set_backdrop(self._viewport_painter);viewport._light=dict(self.preview._light)
    viewport.set_model(self._model,int(self.lod_var.get().split()[-1]));viewport.set_textures(self._preview_pixels)
    info=tk.StringVar(value='Select a sequence to load it.');ttk.Label(right,textvariable=info,wraplength=430,style='Panel.TLabel').pack(fill='x',pady=(10,6))
    controls=ttk.Frame(right,style='Panel.TFrame');controls.pack(fill='x',pady=4)
    blend=tk.IntVar(value=0)
    ttk.Label(controls,text='Variation',style='Muted.Panel.TLabel').pack(side='left')
    self._blend_choice=ttk.Spinbox(controls,from_=0,to=0,textvariable=blend,width=5)
    self._blend_choice.pack(side='left',padx=4)
    play=ttk.Button(controls,text='Play',state='disabled');play.pack(side='left',padx=4)
    position=tk.DoubleVar(value=0)
    timeline=ttk.Scale(right,variable=position,state='disabled',style='Panel.Horizontal.TScale');timeline.pack(fill='x',pady=(8,4))
    footer=ttk.Frame(window,padding=(16,10,16,14));footer.pack(fill='x')
    details=tk.BooleanVar(value=False)
    ttk.Checkbutton(footer,text='Show GUID and link columns',variable=details,
        command=lambda:table.configure(displaycolumns=('name','guid','link','source') if details.get() else ('name','source'))).pack(side='left')
    layout_timer=window.after(100,lambda:body.sashpos(0,int(body.winfo_width()*.56)))
    use=ttk.Button(footer,text='Use animation',state='disabled',style='Accent.TButton');use.pack(side='right')
    picker={'window':window,'preview':viewport,'clip':None,'playing':False,'timer':None,'frame':position}
    self._animation_picker=picker
    def tick():
        picker['timer']=None
        if not picker['playing'] or picker['clip'] is None: return
        clip=picker['clip'];value=int((time.perf_counter()-picker['start'])*clip['fps'])
        if value>=clip['frames']:
            if clip['loop']:value%=clip['frames']
            else:value=clip['frames']-1;picker['playing']=False;play.configure(text='Play')
        if int(position.get())!=value:position.set(value);viewport.set_pose(clip,value)
        if picker['playing']:picker['timer']=window.after(max(1,int(1000/clip['fps'])),tick)
    def stop():
        picker['playing']=False;play.configure(text='Play')
        if picker['timer'] is not None:window.after_cancel(picker['timer']);picker['timer']=None
    def toggle():
        if not picker['clip']:return
        if picker['playing']:stop();return
        if position.get()>=picker['clip']['frames']-1:position.set(0)
        picker['playing']=True;play.configure(text='Pause')
        picker['start']=time.perf_counter()-position.get()/picker['clip']['fps'];tick()
    def seek(value):
        if picker['clip']:
            viewport.set_pose(picker['clip'],int(float(value)))
            if picker['playing']:picker['start']=time.perf_counter()-float(value)/picker['clip']['fps']
    play.configure(command=toggle);timeline.configure(command=seek)
    def close(confirm=False):
        clip=picker['clip'];stop();self._animation_serial+=1;self._animation_picker=None
        window.after_cancel(layout_timer)
        query.trace_remove('write',query_trace);picker.pop('ready',None)
        self._set_busy(False);window.grab_release();window.destroy()
        # Release Tcl variables on UI-thread
        for variable in (query,blend,info,position,details):
            variable.__del__();variable._tk=None
        if confirm and clip is not None:self._apply_animation(clip)
    use.configure(command=lambda:close(True))
    ttk.Button(footer,text='Cancel',command=close).pack(side='right',padx=8)
    window.protocol('WM_DELETE_WINDOW',close);window.bind('<Escape>',lambda e:close())
    def load(*_):
        selected=table.selection()
        if selected and not self._busy:
            stop();picker['clip']=None;use.state(['disabled']);play.state(['disabled']);timeline.state(['disabled'])
            info.set('Loading '+table.item(selected[0],'values')[0]+'…')
            entry.state(['disabled']);self._blend_choice.state(['disabled'])
            self._load_animation(rows[int(selected[0])],blend.get())
    def ready(result,error):
        entry.state(['!disabled']);self._blend_choice.state(['!disabled'])
        if error:info.set(result);return
        picker['clip']=result
        info.set(f'{result["name"]}\n{result["frames"]} frames · {result["fps"]:g} fps · {result["mapped_bones"]} bones')
        self._blend_choice.configure(to=result['blends']-1)
        timeline.configure(to=result['frames']-1);position.set(0);viewport.set_pose(result,0)
        for widget in (use,play,timeline):widget.state(['!disabled'])
        toggle()
    picker['ready']=ready
    def select(*_):
        if self._busy:return
        blend.set(0);self._blend_choice.configure(to=0);load()
    table.bind('<<TreeviewSelect>>',select)
    table.bind('<Button-1>',lambda e:'break' if self._busy else None)
    table.bind('<KeyPress>',lambda e:'break' if self._busy else None)
    self._blend_choice.configure(command=load);self._blend_choice.bind('<Return>',load)
    ttk.Button(controls,text='Reload',style='Ghost.Panel.TButton',command=load).pack(side='left')
    table.bind('<Double-1>',load)
