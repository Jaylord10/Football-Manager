"""
The sun's shadows, drawn by us rather than by Panda3D's ready-made shadows.

Every frame a camera at the sun takes a "depth picture" (how far away everything is, as seen from the sun) into
a texture; the lighting shader (shaders/lit.frag, sun_visible) then asks of each point on the screen: is
something nearer the sun than me?  If so, I'm in shadow.

Panda's own version (DirectionalLight.setShadowCaster) does the same, but makes its picture behind the scenes,
and on Jay's laptop every second or so it came out wrong for a frame (the stands' shadows vanished and rows of
dashes covered the pitch).  Here every part of it is set down plainly: a 24-bit depth picture, cleared and drawn
first thing every frame, by a camera that draws depth and nothing else.
"""
from panda3d.core import (FrameBufferProperties, WindowProperties, GraphicsPipe, GraphicsOutput, Texture,
                          OrthographicLens, Camera, SamplerState, RenderState, ShaderAttrib, ColorWriteAttrib,
                          Shader, LColor)

import os
import sys
# The players' bodies bent onto their skeletons by the graphics card (the shaders) rather than by the processor.
# --cpuskin (or FM_GPUSKIN=0) goes back to the processor doing it.
GPU_SKIN = "--cpuskin" not in sys.argv and os.environ.get("FM_GPUSKIN", "1") != "0"

DEPTH_VERT = """#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; }
"""
# The players' depth: bent onto their skeletons first, as in shaders/lit.vert (given to the sun camera for
# whatever carries the "skin" tag: broadcast3d/players3d.py).
SKIN_DEPTH_VERT = """#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_TransformTable[48];
in vec4 transform_weight;
in uvec4 transform_index;
in vec4 p3d_Vertex;
void main() {
    mat4 m = p3d_TransformTable[transform_index.x] * transform_weight.x
           + p3d_TransformTable[transform_index.y] * transform_weight.y
           + p3d_TransformTable[transform_index.z] * transform_weight.z
           + p3d_TransformTable[transform_index.w] * transform_weight.w;
    gl_Position = p3d_ModelViewProjectionMatrix * (m * p3d_Vertex);
}
"""
DEPTH_FRAG = """#version 130
out vec4 o_color;
void main() { o_color = vec4(1.0); }
"""


def _shadow_sampling(tex):
    """Read as a shadow test (compare with the depth stored), and outside the picture: lit."""
    tex.setMinfilter(SamplerState.FT_shadow)
    tex.setMagfilter(SamplerState.FT_shadow)
    tex.setWrapU(SamplerState.WM_border_color)
    tex.setWrapV(SamplerState.WM_border_color)
    tex.setBorderColor(LColor(1, 1, 1, 1))


def no_sun(render):
    """No sun shadows (an overcast day, the kit pictures): everything counts as lit.  The shader still needs
    something for each of its inputs, so a stand-in picture and camera."""
    tex = Texture("no sun shadow")
    tex.setup2dTexture(1, 1, Texture.T_float, Texture.F_depth_component)
    import struct
    tex.setRamImage(struct.pack("f", 1.0))
    _shadow_sampling(tex)
    render.setShaderInput("sun_shadow", tex)
    render.setShaderInput("suncam", render.attachNewNode(Camera("no sun camera", OrthographicLens())))
    render.setShaderInput("shadow_on", 0.0)


def make(base, sun, size, film, near_far, mask):
    """The sun's depth picture: size x size pixels, the sun camera (at the sun node, looking where it looks)
    seeing film = (width, height) metres, near_far = (near, far) metres from it, and only what's shown to
    mask (hide something from it and it casts no shadow; None: everything).  Sets the shader inputs on base.render."""
    fbp = FrameBufferProperties()
    fbp.setDepthBits(24)
    buf = base.graphicsEngine.makeOutput(base.pipe, "sun shadow", -100, fbp, WindowProperties.size(size, size),
                                         GraphicsPipe.BF_refuse_window, base.win.getGsg(), base.win)
    if buf is None:                                    # (no offscreen pictures on this machine: no sun shadows)
        print("sun shadow: couldn't make the depth picture - no shadows")
        no_sun(base.render)
        return None
    tex = Texture("sun shadow")
    buf.addRenderTexture(tex, GraphicsOutput.RTM_bind_or_copy, GraphicsOutput.RTP_depth)
    _shadow_sampling(tex)
    buf.setSort(-100)                                  # (drawn before the screen, every frame)
    buf.setClearColorActive(False)
    buf.setClearDepthActive(True)
    buf.setClearDepth(1.0)
    lens = OrthographicLens()
    lens.setFilmSize(*film)
    lens.setNearFar(*near_far)
    cn = Camera("sun camera", lens)
    if mask is not None:
        cn.setCameraMask(mask)
    depth_only = Shader.make(Shader.SL_GLSL, DEPTH_VERT, DEPTH_FRAG)
    cn.setInitialState(RenderState.make(ShaderAttrib.make(depth_only), ColorWriteAttrib.make(ColorWriteAttrib.C_off),
                                        1000))
    if GPU_SKIN:                                       # (the players: their own depth shader, skinned on the card)
        sk = ShaderAttrib.make(Shader.make(Shader.SL_GLSL, SKIN_DEPTH_VERT, DEPTH_FRAG), 1001)
        sk = sk.setFlag(ShaderAttrib.F_hardware_skinning, True)
        cn.setTagStateKey("skin")
        cn.setTagState("1", RenderState.make(sk, ColorWriteAttrib.make(ColorWriteAttrib.C_off), 1001))
    cam = sun.attachNewNode(cn)
    dr = buf.makeDisplayRegion()
    dr.setCamera(cam)
    base.render.setShaderInput("sun_shadow", tex)
    base.render.setShaderInput("suncam", cam)
    base.render.setShaderInput("shadow_on", 1.0)
    return buf
