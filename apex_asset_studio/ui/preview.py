import math
import numpy as np
from OpenGL import GL
from pyopengltk import OpenGLFrame


def pose_matrices(bones, positions, rotations, scales):
    matrices=np.zeros((len(bones),4,4),dtype=np.float32)
    for i,bone in enumerate(bones):
        x,y,z,w=rotations[i]
        matrices[i,:3,:3]=np.array(((1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)),
            (2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)),
            (2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y))))*scales[i]
        matrices[i,:3,3]=positions[i]; matrices[i,3,3]=1
        if bone.parent>=0: matrices[i]=matrices[bone.parent]@matrices[i]
    return matrices


class ModelPreview(OpenGLFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.vertices=np.empty((0,3),dtype=np.float32)
        self.normals=self.vertices.copy()
        self.faces=np.empty(0,dtype=np.uint32)
        self.yaw=-.35; self.pitch=-.05; self.zoom=1.; self._drag=None
        self.pan=np.zeros(2,dtype=np.float32)
        self._background='#16191d'; self._pending=None
        self._textures={}; self._new_textures={}; self._texture_key=None
        self.bind('<ButtonPress-1>',self._down)
        self.bind('<B1-Motion>',self._move)
        self.bind('<MouseWheel>',self._wheel)
        for button in (2,3):
            self.bind(f'<ButtonPress-{button}>',self._pan_down)
            self.bind(f'<B{button}-Motion>',self._pan_move)
        self.bind('<Shift-ButtonPress-1>',self._pan_down)
        self.bind('<Shift-B1-Motion>',self._pan_move)

    @property
    def has_geometry(self): return len(self.vertices)>0

    def initgl(self):
        self.tkMakeCurrent()
        self.renderer=GL.glGetString(GL.GL_RENDERER).decode()
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glShadeModel(GL.GL_SMOOTH)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glLightfv(GL.GL_LIGHT0,GL.GL_POSITION,(-.3,.5,1,0))
        GL.glLightfv(GL.GL_LIGHT0,GL.GL_AMBIENT,(.3,.3,.3,1))
        GL.glLightfv(GL.GL_LIGHT1,GL.GL_POSITION,(.5,.3,-1,0))
        GL.glLightfv(GL.GL_LIGHT1,GL.GL_DIFFUSE,(.5,.5,.5,1))
        GL.glMaterialfv(GL.GL_FRONT_AND_BACK,GL.GL_AMBIENT_AND_DIFFUSE,(.72,.77,.82,1))
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)
        GL.glEnableClientState(GL.GL_TEXTURE_COORD_ARRAY)
        GL.glEnable(GL.GL_FRAMEBUFFER_SRGB)
        self.schedule()

    def set_palette(self, background, foreground, muted):
        self._background=background; self.schedule()

    def clear(self, message=''):
        self.vertices=np.empty((0,3),dtype=np.float32)
        self.faces=np.empty(0,dtype=np.uint32)
        self._new_textures={};self._texture_key=None;self._delete_textures=True
        self.schedule()

    def set_model(self, model, lod):
        meshes=[m for m in model.lods[lod] if m.positions and m.indices]
        self.vertices=np.asarray([p for m in meshes for p in m.positions],dtype=np.float32)
        self.normals=np.asarray([n for m in meshes for n in m.normals],dtype=np.float32)
        self.uvs=np.asarray([m.uvs[i][0] if m.uvs and m.uvs[i] else (0,0)
                            for m in meshes for i in range(len(m.positions))],dtype=np.float32)
        self.draw_ranges=[]
        faces=[]; offset=0
        for mesh in meshes:
            self.draw_ranges.append((mesh.material,len(faces),len(mesh.indices),bool(mesh.uvs)))
            faces.extend((np.asarray(mesh.indices,dtype=np.uint32).reshape(-1,3)[:,[0,2,1]]+offset).ravel())
            offset+=len(mesh.positions)
        self.faces=np.asarray(faces,dtype=np.uint32)
        if self._texture_key!=(model.guid,model.family):
            self._new_textures={};self._delete_textures=True;self.pan[:]=0
        self._texture_key=(model.guid,model.family)
        self.bones=model.bones
        self.bind_vertices=np.column_stack((self.vertices,np.ones(len(self.vertices),dtype=np.float32)))
        self.bind_normals=self.normals.copy()
        influences=[w for m in meshes for w in m.weights]
        count=max(map(len,influences),default=0)
        self.joints=np.zeros((len(influences),count),dtype=np.int32)
        self.weights=np.zeros((len(influences),count),dtype=np.float32)
        for i,values in enumerate(influences):
            for j,(bone,weight) in enumerate(values): self.joints[i,j]=bone; self.weights[i,j]=weight
        self.inverse_bind=np.tile(np.eye(4,dtype=np.float32),(len(model.bones),1,1))
        for i,bone in enumerate(model.bones): self.inverse_bind[i,:3]=np.asarray(bone.inverse_bind).reshape(3,4)
        self.center=(self.vertices.min(axis=0)+self.vertices.max(axis=0))/2
        self.span=max(float(np.ptp(self.vertices,axis=0).max()),.001)
        self.zoom=1.; self.schedule()

    def set_textures(self, textures):
        if self._new_textures is None: self._new_textures={}
        self._new_textures.update(textures);self.schedule()

    def reset_view(self):
        self.yaw=-.35;self.pitch=-.05;self.zoom=1.;self.pan[:]=0;self.schedule()

    def destroy(self):
        if self._pending is not None:self.after_cancel(self._pending);self._pending=None
        if self.context_created:
            from OpenGL import WGL
            WGL.wglMakeCurrent(0,0)
            WGL.wglDeleteContext(self._OpenGLFrame__context)
        super().destroy()

    def set_pose(self, animation, frame):
        if animation is None:
            self.vertices=self.bind_vertices[:,:3].copy(); self.normals=self.bind_normals.copy()
        else:
            world=pose_matrices(self.bones,animation['positions'][frame],animation['rotations'][frame],animation['scales'][frame])
            skin=world@self.inverse_bind
            transform=np.einsum('ni,nijk->njk',self.weights,skin[self.joints],optimize=True)
            self.vertices=np.ascontiguousarray(np.einsum('nij,nj->ni',transform,self.bind_vertices)[:,:3],dtype=np.float32)
            self.normals=np.ascontiguousarray(np.einsum('nij,nj->ni',transform[:,:3,:3],self.bind_normals),dtype=np.float32)
        self.center=(self.vertices.min(axis=0)+self.vertices.max(axis=0))/2
        self.schedule()

    def schedule(self):
        if self._pending is None: self._pending=self.after(8,self._render)

    def _render(self):
        self._pending=None
        if self.context_created and self.winfo_ismapped(): self._display()

    def _display(self):
        if self.context_created and self.winfo_ismapped(): super()._display()

    def tkResize(self,event):
        self.width,self.height=event.width,event.height
        if self.context_created and self.winfo_ismapped():
            self.tkMakeCurrent();GL.glViewport(0,0,self.width,self.height);self.initgl()

    def _down(self,event): self._drag=(event.x,event.y,self.yaw,self.pitch)

    def _move(self,event):
        if not self.has_geometry or not self._drag or len(self._drag)!=4: return
        x,y,yaw,pitch=self._drag
        self.yaw=yaw+(event.x-x)*.01
        self.pitch=max(-1.5,min(1.5,pitch+(event.y-y)*.01)); self.schedule()

    def _wheel(self,event):
        self.zoom=max(.2,min(8,self.zoom*(1.1 if event.delta>0 else .9))); self.schedule()

    def _pan_down(self,event):
        self._drag=(event.x,event.y,self.pan.copy());return 'break'

    def _pan_move(self,event):
        if not self.has_geometry or not self._drag or len(self._drag)!=3: return 'break'
        x,y,pan=self._drag
        scale=self.span/.82/self.zoom/max(1,min(self.winfo_width(),self.winfo_height()))
        self.pan=pan+np.asarray((event.x-x,y-event.y),dtype=np.float32)*scale
        self.schedule();return 'break'

    def redraw(self):
        if getattr(self,'_delete_textures',False):
            if self._textures: GL.glDeleteTextures(list(self._textures.values()))
            self._textures={};self._delete_textures=False
        if self._new_textures is not None:
            for material,(width,height,pixels,srgb) in self._new_textures.items():
                if material in self._textures: GL.glDeleteTextures([self._textures[material]])
                texture=GL.glGenTextures(1);self._textures[material]=texture
                GL.glBindTexture(GL.GL_TEXTURE_2D,texture)
                GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_LINEAR)
                GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_LINEAR)
                GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_SRGB8_ALPHA8 if srgb else GL.GL_RGBA8,width,height,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,pixels)
            self._new_textures=None
        color=self.winfo_rgb(self._background)
        color=[v/65535 for v in color]
        GL.glClearColor(*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in color),1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT|GL.GL_DEPTH_BUFFER_BIT)
        if not self.has_geometry: return
        w,h=max(self.winfo_width(),1),max(self.winfo_height(),1)
        GL.glViewport(0,0,w,h)
        extent=self.span/.82/self.zoom/2
        GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity()
        GL.glOrtho(-extent*w/min(w,h),extent*w/min(w,h),-extent*h/min(w,h),extent*h/min(w,h),-self.span*10,self.span*10)
        GL.glMatrixMode(GL.GL_MODELVIEW); GL.glLoadIdentity()
        GL.glTranslatef(*self.pan,0)
        GL.glRotatef(math.degrees(self.pitch),1,0,0)
        GL.glRotatef(math.degrees(self.yaw),0,1,0)
        GL.glTranslatef(*(-self.center))
        GL.glVertexPointer(3,GL.GL_FLOAT,0,self.vertices)
        GL.glNormalPointer(GL.GL_FLOAT,0,self.normals)
        GL.glTexCoordPointer(2,GL.GL_FLOAT,0,self.uvs)
        for material,start,count,has_uv in self.draw_ranges:
            if material in self._textures and has_uv:
                GL.glEnable(GL.GL_TEXTURE_2D);GL.glBindTexture(GL.GL_TEXTURE_2D,self._textures[material])
                GL.glEnable(GL.GL_ALPHA_TEST);GL.glAlphaFunc(GL.GL_GREATER,0.)
            else: GL.glDisable(GL.GL_TEXTURE_2D);GL.glDisable(GL.GL_ALPHA_TEST)
            GL.glDrawElements(GL.GL_TRIANGLES,count,GL.GL_UNSIGNED_INT,self.faces[start:start+count])
        GL.glDisable(GL.GL_TEXTURE_2D);GL.glDisable(GL.GL_ALPHA_TEST)
