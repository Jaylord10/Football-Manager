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
uniform mat4 p3d_ViewMatrix;
uniform sampler2D p3d_Texture1;        // (fine grass, tiled over the pitch: detail_amt 0 elsewhere)
uniform float detail_amt;
uniform vec2 detail_scale;
in vec4 v_shadow;
in vec3 v_normal;
in vec4 v_color;
in vec2 v_uv;
in vec2 v_uv1;
in vec3 v_view;
out vec4 o_color;

// The players' kits, worked out for every pixel from where it is on the body (broadcast3d/players3d.py: the
// body's standing position is in the texture coordinates - v_uv = (x, z), v_uv1.x = y; he faces -y, his right
// is -x).  kit_on 0: not a player.
uniform float kit_on;
uniform vec4 kit_shirt, kit_trim, kit_shorts, kit_socks, kit_socktop, kit_skin, kit_hair, kit_gloves;
uniform vec4 kit_info;                  // (pattern 0 none 1 hoops 2 stripes 3 pinstripe 4 band 5 halves 6 sash
                                        //  7 sleeves, keeper, has crest, -)

vec3 shirt_at(float x, float y, float z, bool torso) {
    int pat = int(kit_info.x + 0.5);
    vec3 s = kit_shirt.rgb, t = kit_trim.rgb;
    if (pat == 7) return torso ? s : t;
    if (!torso) return s;
    if (pat == 1) return mod(floor((z - 0.97) / 0.105), 2.0) > 0.5 ? t : s;
    if (pat == 2) return mod(floor((x + 0.5) / 0.075), 2.0) > 0.5 ? t : s;
    if (pat == 3) return mod(x + 0.5, 0.055) < 0.009 ? t : s;
    if (pat == 4) return (z > 1.24 && z < 1.33) ? t : s;
    if (pat == 5) return x > 0.0 ? t : s;
    if (pat == 6) return abs(x * (y < 0.0 ? 1.0 : -1.0) - (z - 1.18) * 0.85) < 0.07 ? t : s;
    return s;
}

vec4 kit_colour() {
    float x = v_uv.x, z = v_uv.y, y = v_uv1.x, ax = abs(x);
    bool keeper = kit_info.y > 0.5;
    if (z < 0.075) return vec4(0.09, 0.09, 0.10, 1.0);                               // boots
    if (z < 0.40) return kit_socks;
    if (z < 0.46) return kit_socktop;
    if (z < 0.66) return kit_skin;
    if (z < 0.97 && ax < 0.24) {                                                    // shorts, a stripe down the side
        return (ax > 0.205 && z > 0.70) ? kit_trim : kit_shorts;
    }
    if (z < 1.49 && ax < 0.36) {
        if (z > 1.465 && ax < 0.085) return kit_trim;                               // the collar
        if (y < 0.0 && z > 1.40 && ax < 0.05 - (1.465 - z) * 0.6 && ax > 0.032 - (1.465 - z) * 0.6)
            return kit_trim;                                                        // (a V-neck's trim)
        if (y > 0.0 && ax < 0.15 && z > 1.10 && z < 1.44) {                         // name and number on the back
            vec4 n = texture(p3d_Texture0, vec2((0.15 - x) / 0.30, (z - 1.10) / 0.34));
            if (n.a > 0.5) return vec4(n.rgb, 1.0);
        }
        if (kit_info.z > 0.5 && y < 0.0 && x > 0.04 && x < 0.15 && z > 1.27 && z < 1.38) {   // the club crest
            vec4 c = texture(p3d_Texture1, vec2((x - 0.04) / 0.11, (z - 1.27) / 0.11));
            if (c.a > 0.5) return vec4(c.rgb, 1.0);
        }
        return vec4(shirt_at(x, y, z, ax < 0.24), 1.0);
    }
    if (keeper && z < 1.49 && ax < 0.70) return vec4(shirt_at(x, y, z, false), 1.0);   // a keeper's long sleeves
    if (keeper && z < 1.49) return kit_gloves;                                       // and gloves
    if (z < 1.49 && ax < 0.40) return kit_trim;                                    // the sleeve's hem
    if (z >= 1.72 || (z > 1.62 && y > 0.02)) return kit_hair;
    return kit_skin;
}

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
    vec4 base = kit_on > 0.5 ? kit_colour() * p3d_ColorScale
                             : (texture(p3d_Texture0, v_uv) + p3d_TexAlphaOnly) * v_color * p3d_ColorScale;
    float nl = length(v_normal);
    float lambert = 1.0;
    if (nl > 0.01) {
        vec3 n = v_normal / nl;
        if (!gl_FrontFacing) n = -n;
        lambert = max(dot(n, normalize(p3d_LightSource[0].position.xyz)), 0.0);
    }
    // Sky light: brighter on what faces up, a little darker on what faces down (the grass bounces less).
    float sky = 1.0;
    if (nl > 0.01) {
        vec3 up = normalize(mat3(p3d_ViewMatrix) * vec3(0.0, 0.0, 1.0));
        vec3 n2 = v_normal / nl;
        if (!gl_FrontFacing) n2 = -n2;
        sky = 0.85 + 0.15 * dot(n2, up);
    }
    vec3 light = p3d_LightModel.ambient.rgb * sky + p3d_LightSource[0].diffuse.rgb * lambert * sun_visible();
    if (detail_amt > 0.0)
        base.rgb *= mix(vec3(1.0), texture(p3d_Texture1, v_uv * detail_scale).rgb * 2.0, detail_amt);
    vec3 col = base.rgb * light;
    float fog = clamp(exp(-length(v_view) * p3d_Fog.density), 0.0, 1.0);
    o_color = vec4(mix(p3d_Fog.color.rgb, col, fog), base.a);
}
