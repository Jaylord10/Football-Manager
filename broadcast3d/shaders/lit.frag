#version 130
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform vec4 p3d_TexAlphaOnly;          // (text glyphs are alpha-only textures)
uniform struct p3d_LightModelParameters { vec4 ambient; } p3d_LightModel;
uniform struct p3d_LightSourceParameters {
    vec4 position;
    vec4 diffuse;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];
uniform struct p3d_FogParameters { vec4 color; float density; } p3d_Fog;
uniform float shadow_bias;
uniform float shadow_texel;

in vec4 v_shadow;
in vec3 v_normal;
in vec4 v_color;
in vec2 v_uv;
in vec3 v_view;
out vec4 o_color;

float sun_visible() {
    // A soft edge: 3 x 3 samples of the shadow map around this point.
    vec3 p = v_shadow.xyz / v_shadow.w;
    p.z -= shadow_bias;
    float s = 0.0;
    for (int x = -1; x <= 1; ++x)
        for (int y = -1; y <= 1; ++y)
            s += texture(p3d_LightSource[0].shadowMap, p + vec3(x, y, 0) * shadow_texel);
    return s / 9.0;
}

void main() {
    vec4 base = (texture(p3d_Texture0, v_uv) + p3d_TexAlphaOnly) * v_color * p3d_ColorScale;
    float nl = length(v_normal);
    float lambert = 1.0;
    if (nl > 0.01) {
        vec3 n = v_normal / nl;
        if (!gl_FrontFacing) n = -n;
        lambert = max(dot(n, normalize(p3d_LightSource[0].position.xyz)), 0.0);
    }
    vec3 light = p3d_LightModel.ambient.rgb + p3d_LightSource[0].diffuse.rgb * lambert * sun_visible();
    vec3 col = base.rgb * light;
    float fog = clamp(exp(-length(v_view) * p3d_Fog.density), 0.0, 1.0);
    o_color = vec4(mix(p3d_Fog.color.rgb, col, fog), base.a);
}
