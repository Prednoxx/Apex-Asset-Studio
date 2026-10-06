import math
import numpy as np
from OpenGL import GL
from PIL import Image
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


VERTEX_SHADER = '''
#version 120
varying vec3 normal_view;
varying vec2 uv;
void main() {
    normal_view = gl_NormalMatrix * gl_Normal;
    uv = gl_MultiTexCoord0.xy;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
'''

# Lighting is camera-relative (the key light stays upper-left as you orbit): wrapped diffuse key light, a sky/ground
# hemisphere ambient tinted by the theme, a soft rim light and a small specular highlight. Output is linear; the
# sRGB framebuffer encodes it. pass 0 draws opaque texels (alpha >= 0.5) with depth writes, pass 1 blends the soft
# edges of hair and glass (alpha < 0.5) on top without writing depth.
FRAGMENT_SHADER = '''
#version 120
uniform sampler2D tex;
uniform bool textured;
uniform int pass;
uniform vec3 base_color;
uniform vec3 sky;
uniform vec3 ground;
uniform vec3 rim_color;
varying vec3 normal_view;
varying vec2 uv;
void main() {
    vec4 color = textured ? texture2D(tex, uv) : vec4(base_color, 1.0);
    if (pass == 0 && color.a < 0.5) discard;
    if (pass == 1 && (color.a >= 0.5 || color.a < 0.02)) discard;
    vec3 n = normalize(normal_view);
    if (n.z < 0.0) n = -n;  // two-sided: the visible side of a thin surface faces the camera
    vec3 key = normalize(vec3(-0.45, 0.65, 0.6));
    float wrap = max((dot(n, key) + 0.35) / 1.35, 0.0);
    float fill = max(dot(n, normalize(vec3(0.6, 0.1, 0.3))), 0.0) * 0.25;
    vec3 ambient = mix(ground, sky, n.y * 0.5 + 0.5);
    float rim = pow(1.0 - max(n.z, 0.0), 3.0) * 0.35;
    float spec = pow(max(dot(n, normalize(key + vec3(0.0, 0.0, 1.0))), 0.0), 40.0) * 0.15;
    vec3 lit = color.rgb * (ambient * 0.55 + wrap * vec3(1.0, 0.97, 0.92) * 0.85 + fill) + spec + rim * rim_color;
    gl_FragColor = vec4(lit, pass == 1 ? color.a : 1.0);
}
'''


def _linear(rgb):
    return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]


class ModelPreview(OpenGLFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.vertices=np.empty((0,3),dtype=np.float32)
        self.normals=self.vertices.copy()
        self.faces=np.empty(0,dtype=np.uint32)
        self.yaw=-.35; self.pitch=.18; self.zoom=1.; self._drag=None
        self.pan=np.zeros(2,dtype=np.float32)
        self._background='#16191d'; self._pending=None
        self._textures={}; self._new_textures={}; self._texture_key=None
        # Backdrop art: painter(width, height, message) -> PIL RGBA image, drawn behind the model as one texture.
        # Empty-state messages ('Select an item…') are painted into it, so they sit on the art without a box.
        self._painter=None; self.message=''; self.badge=''; self._bg_key=None; self._bg_texture=None; self._bg_timer=None
        self._program=None; self._shader_failed=False
        self._light=dict(sky=(.55,.6,.68), ground=(.12,.11,.1), rim=(.5,.55,.65), shadow=.45)
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
        if self._program is None and not self._shader_failed:
            try:
                from OpenGL.GL import shaders
                self._program=shaders.compileProgram(shaders.compileShader(VERTEX_SHADER,GL.GL_VERTEX_SHADER),
                                                     shaders.compileShader(FRAGMENT_SHADER,GL.GL_FRAGMENT_SHADER),validate=False)
                self._uniforms={n:GL.glGetUniformLocation(self._program,n) for n in ('tex','textured','pass','base_color','sky','ground','rim_color')}
            except Exception as exc:  # very old drivers: keep the fixed-function path
                self._shader_failed=True; self.shader_error=str(exc)
        self.schedule()

    def set_palette(self, background):
        self._background=background; self.schedule()

    def set_lighting(self, sky, ground, rim, light_theme):
        """Theme-tinted ambient light (hex colors) and how dark the ground shadow is."""
        self._light=dict(sky=tuple(_linear(self._rgb(sky))), ground=tuple(_linear(self._rgb(ground))),
                         rim=tuple(_linear(self._rgb(rim))), shadow=.38 if light_theme else .6)
        self.schedule()

    def set_badge(self, text):
        """Small caption in the corner of the view (the playing animation)."""
        if text!=self.badge: self.badge=text; self._bg_key=None; self.schedule()

    def set_backdrop(self, painter):
        self._painter=painter; self._bg_key=None; self.schedule()

    def _message(self, text):
        if text!=self.message: self.message=text; self._bg_key=None

    def clear(self, message=''):
        self.vertices=np.empty((0,3),dtype=np.float32)
        self.faces=np.empty(0,dtype=np.uint32)
        self._new_textures={};self._texture_key=None;self._delete_textures=True
        self._message(message)
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
        lo,hi=self.vertices.min(axis=0),self.vertices.max(axis=0)  # ground shadow: under the feet, sized to the footprint
        self.floor=(float(lo[1]),float((lo[0]+hi[0])/2),float((lo[2]+hi[2])/2),max(float(hi[0]-lo[0])*.9,float(hi[2]-lo[2])*.9,self.span*.38))
        self.zoom=1.; self._message(''); self.schedule()

    def set_textures(self, textures):
        if self._new_textures is None: self._new_textures={}
        self._new_textures.update(textures);self.schedule()

    def reset_view(self):
        self.yaw=-.35;self.pitch=.18;self.zoom=1.;self.pan[:]=0;self.schedule()

    def destroy(self):
        if self._pending is not None:self.after_cancel(self._pending);self._pending=None
        if self._bg_timer is not None:self.after_cancel(self._bg_timer);self._bg_timer=None
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

    def _rgb(self, color): return [v/65535 for v in self.winfo_rgb(color)]

    def _refresh_backdrop(self, w, h):
        """Repaint the backdrop texture when the size, message or theme changes. While the view is being resized
        the old texture is stretched and the repaint waits until resizing pauses."""
        key=(w,h,self.message,self.badge,self._painter)
        if self._painter is None or key==self._bg_key: return
        if self._bg_texture is not None and self._bg_key and self._bg_key[2:]==key[2:] and self._bg_timer is None:
            self._bg_timer=self.after(140,self._resized); return
        if self._bg_timer is not None: return
        image=self._painter(w,h,self.message,self.badge).convert('RGBA').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if self._bg_texture is None: self._bg_texture=GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D,self._bg_texture)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_WRAP_S,GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_WRAP_T,GL.GL_CLAMP_TO_EDGE)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT,4)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_SRGB8_ALPHA8,image.width,image.height,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,image.tobytes())
        self._bg_key=key

    def _resized(self):
        self._bg_timer=None; self._bg_key=None; self.schedule()

    def _draw_backdrop(self, w, h):
        self._refresh_backdrop(w,h)
        if self._bg_texture is None: return
        GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity()
        GL.glMatrixMode(GL.GL_MODELVIEW); GL.glLoadIdentity()
        GL.glDisable(GL.GL_LIGHTING); GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_TEXTURE_2D); GL.glBindTexture(GL.GL_TEXTURE_2D,self._bg_texture)
        GL.glColor4f(1,1,1,1)
        GL.glBegin(GL.GL_QUADS)
        for u,v in ((0,0),(1,0),(1,1),(0,1)): GL.glTexCoord2f(u,v); GL.glVertex2f(u*2-1,v*2-1)
        GL.glEnd()
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glEnable(GL.GL_LIGHTING); GL.glEnable(GL.GL_DEPTH_TEST)

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
        color=[v/65535 for v in self.winfo_rgb(self._background)]
        GL.glClearColor(*_linear(color),1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT|GL.GL_DEPTH_BUFFER_BIT)
        w,h=max(self.winfo_width(),1),max(self.winfo_height(),1)
        GL.glViewport(0,0,w,h)
        self._draw_backdrop(w,h)
        if self.has_geometry: self._draw_model(w,h)

    def _draw_model(self, w, h):
        extent=self.span/.82/self.zoom/2
        GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity()
        GL.glOrtho(-extent*w/min(w,h),extent*w/min(w,h),-extent*h/min(w,h),extent*h/min(w,h),-self.span*10,self.span*10)
        GL.glMatrixMode(GL.GL_MODELVIEW); GL.glLoadIdentity()
        GL.glTranslatef(*self.pan,0)
        GL.glRotatef(math.degrees(self.pitch),1,0,0)
        GL.glRotatef(math.degrees(self.yaw),0,1,0)
        GL.glTranslatef(*(-self.center))
        self._draw_shadow()
        GL.glVertexPointer(3,GL.GL_FLOAT,0,self.vertices)
        GL.glNormalPointer(GL.GL_FLOAT,0,self.normals)
        GL.glTexCoordPointer(2,GL.GL_FLOAT,0,self.uvs)
        if self._program is None: return self._draw_fixed()
        u=self._uniforms; light=self._light
        GL.glUseProgram(self._program)
        GL.glUniform1i(u['tex'],0); GL.glUniform3f(u['base_color'],.42,.46,.52)
        GL.glUniform3f(u['sky'],*light['sky']); GL.glUniform3f(u['ground'],*light['ground']); GL.glUniform3f(u['rim_color'],*light['rim'])
        GL.glActiveTexture(GL.GL_TEXTURE0)
        for render_pass in (0,1):
            GL.glUniform1i(u['pass'],render_pass)
            if render_pass:
                GL.glEnable(GL.GL_BLEND); GL.glBlendFunc(GL.GL_SRC_ALPHA,GL.GL_ONE_MINUS_SRC_ALPHA); GL.glDepthMask(GL.GL_FALSE)
            for material,start,count,has_uv in self.draw_ranges:
                textured=material in self._textures and has_uv
                if render_pass and not textured: continue  # untextured meshes are fully opaque
                GL.glUniform1i(u['textured'],int(textured))
                if textured: GL.glBindTexture(GL.GL_TEXTURE_2D,self._textures[material])
                GL.glDrawElements(GL.GL_TRIANGLES,count,GL.GL_UNSIGNED_INT,self.faces[start:start+count])
        GL.glDepthMask(GL.GL_TRUE); GL.glDisable(GL.GL_BLEND)
        GL.glUseProgram(0)

    def _draw_fixed(self):
        """Fallback for drivers without GLSL: the original fixed-function lighting."""
        for material,start,count,has_uv in self.draw_ranges:
            if material in self._textures and has_uv:
                GL.glEnable(GL.GL_TEXTURE_2D);GL.glBindTexture(GL.GL_TEXTURE_2D,self._textures[material])
                GL.glEnable(GL.GL_ALPHA_TEST);GL.glAlphaFunc(GL.GL_GREATER,0.)
            else: GL.glDisable(GL.GL_TEXTURE_2D);GL.glDisable(GL.GL_ALPHA_TEST)
            GL.glDrawElements(GL.GL_TRIANGLES,count,GL.GL_UNSIGNED_INT,self.faces[start:start+count])
        GL.glDisable(GL.GL_TEXTURE_2D);GL.glDisable(GL.GL_ALPHA_TEST)

    def _draw_shadow(self):
        """Soft contact shadow: a disc on the ground plane that fades out from the middle of the footprint."""
        floor=getattr(self,'floor',None)
        if not floor: return
        y,cx,cz,radius=floor; strength=self._light['shadow']
        GL.glDisable(GL.GL_LIGHTING); GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glEnable(GL.GL_BLEND); GL.glBlendFunc(GL.GL_SRC_ALPHA,GL.GL_ONE_MINUS_SRC_ALPHA); GL.glDepthMask(GL.GL_FALSE)
        for ring in range(6):  # concentric fans give a smooth falloff
            inner,outer=ring/6,(ring+1)/6
            a0,a1=strength*(1-inner)**2,strength*(1-outer)**2
            GL.glBegin(GL.GL_TRIANGLE_STRIP)
            for k in range(49):
                angle=k/48*math.tau; c,s_=math.cos(angle),math.sin(angle)
                GL.glColor4f(0,0,0,a0); GL.glVertex3f(cx+c*radius*inner,y,cz+s_*radius*inner)
                GL.glColor4f(0,0,0,a1); GL.glVertex3f(cx+c*radius*outer,y,cz+s_*radius*outer)
            GL.glEnd()
        GL.glDepthMask(GL.GL_TRUE); GL.glDisable(GL.GL_BLEND); GL.glColor4f(1,1,1,1)
        GL.glEnable(GL.GL_LIGHTING)
