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
in vec3 v_world;
out vec4 o_color;

// The players' kits, worked out for every pixel from where it is on the body (broadcast3d/players3d.py: the
// body's standing position is in the texture coordinates - v_uv = (x, z), v_uv1.x = y; he faces -y, his right
// is -x).  kit_on 0: not a player.
uniform float night_on;                 // (floodlights: bright over the pitch, falling away beyond it)
uniform float crowd_amt;                // (the crowd: how much they're bobbing about - lots after a goal)
uniform float osg_FrameTime;
uniform float kit_on;
uniform vec4 kit_shirt, kit_trim, kit_shorts, kit_socks, kit_socktop, kit_skin, kit_hair, kit_gloves;
uniform vec4 kit_extra;                 // (collar: 0 round, 1 V-neck, 2 grandad, 3 polo)
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

// The head: hair (his style - kit_info.w: 0 short, 1 shaved, 2 longer, +4 a beard), and a simple face.
vec4 head_colour(float x, float y, float z, float ax) {
    float style = mod(kit_info.w, 4.0);
    bool beard = kit_info.w >= 3.5;
    // The hairline: high at the front (a little higher at the temples), down to above the ears at the sides,
    // and down the back of the head to the nape (lower for longer hair).
    float back = style > 1.5 ? 1.545 : 1.605;
    float frontline = 1.728 - 0.02 * smoothstep(0.03, 0.065, ax);
    float l = y < -0.02 ? mix(1.668, frontline, smoothstep(-0.02, -0.08, y))
                        : mix(1.668, back, smoothstep(-0.02, 0.05, y));
    bool ear = ax > 0.066 && z > 1.61 && z < 1.674 && abs(y + 0.005) < 0.032;
    if (z > l && !(ear && style < 1.5)) {
        if (style > 0.5 && style < 1.5) return mix(kit_skin, kit_hair, 0.5);   // (shaved close)
        return kit_hair;
    }
    if (y < -0.092) {                                               // the face
        vec2 e = vec2(ax - 0.033, z - 1.655);
        float r = length(e);
        vec2 lid = vec2(e.x / 0.0105, e.y / 0.0062);
        if (dot(lid, lid) < 1.0) {                                  // eyes (almond-shaped): white, iris, pupil
            if (r < 0.0026) return vec4(0.03, 0.03, 0.03, 1.0);
            if (r < 0.0056) return vec4(0.27, 0.18, 0.11, 1.0);
            return vec4(0.84, 0.82, 0.78, 1.0);
        }
        if (dot(lid, lid) < 1.35 && e.y > 0.0) return vec4(kit_skin.rgb * 0.55, 1.0);   // (the upper lid's line)
        float bz = 1.6775 + 0.0035 * (1.0 - pow((ax - 0.036) / 0.022, 2.0));
        if (ax > 0.013 && ax < 0.058 && abs(z - bz) < 0.0042) return mix(kit_hair, kit_skin, 0.15);   // brows
        vec2 lp = vec2(ax / 0.022, (z - 1.588) / 0.0068);
        if (dot(lp, lp) < 1.0) {                                    // lips (and the line between them)
            if (abs(z - 1.5882) < 0.0009) return vec4(kit_skin.rgb * vec3(0.45, 0.32, 0.3), 1.0);
            return vec4(kit_skin.rgb * vec3(0.8, 0.6, 0.57), 1.0);
        }
    }
    if (beard && y < 0.0) {                                         // a beard: along the jaw and chin, a
        float top = 1.596 + 0.018 * smoothstep(0.02, 0.06, ax);     //  moustache, soft at its edges
        float a = smoothstep(top, top - 0.008, z) * smoothstep(1.535, 1.55, z);
        vec2 lp = vec2(ax / 0.024, (z - 1.588) / 0.0085);
        a *= smoothstep(1.0, 1.4, dot(lp, lp)) * smoothstep(0.0, -0.03, y);
        if (ax < 0.026 && z > 1.596 && z < 1.606) a = 0.9;          // (the moustache)
        if (a > 0.0) return mix(kit_skin, kit_hair, 0.78 * a);
    }
    return kit_skin;
}

vec4 kit_colour() {
    float x = v_uv.x, z = v_uv.y, y = v_uv1.x, ax = abs(x);
    bool keeper = kit_info.y > 0.5;
    if (z < 0.10 || (z < 0.13 && v_uv1.x < -0.03)) return vec4(0.09, 0.09, 0.10, 1.0);   // boots
    if (kit_extra.y > 0.5 && z < 0.927 && ax < 0.25) return kit_shorts;             // (trousers: the managers)
    if (kit_extra.w > 0.5 && z < 1.49 && ax >= 0.66) return kit_gloves;             // (gloves on a cold day)
    if (kit_extra.z > 0.5 && z < 1.49 && ax > 0.24 && ax < 0.66 && !(z > 1.43 && ax < 0.09)) {
        if (kit_extra.y > 0.5) return kit_shirt;                                    // (a coat / training top)
        return ax > 0.63 ? kit_trim : vec4(shirt_at(x, y, z, false), 1.0);         // (long sleeves, cuffed)
    }
    if (z < 0.40) return kit_socks;
    if (z < 0.46) return kit_socktop;
    if (z < 0.619) return kit_skin;
    if (z < 0.927 && ax < 0.25) {                                                   // shorts, a stripe down the side
        float c = 0.084 + (0.955 - z) / 0.333 * 0.028;
        float dx = ax - c;
        return (dx / max(length(vec2(dx, y)), 1e-4) > 0.975 && dx > 0.0) ? kit_trim : kit_shorts;
    }
    float top = 1.49 + 0.045 * smoothstep(0.1, 0.2, ax);                            // (the shoulders)
    if (z < top && ax < 0.355) {
        int col = int(kit_extra.x + 0.5);
        float cz = col == 3 ? 1.445 : (col == 2 ? 1.455 : 1.465);                   // the collar (a polo's is deeper)
        if (z > cz && ax < (col == 3 ? 0.10 : 0.085)) return kit_trim;
        if (col == 1 && y < 0.0 && z > 1.40 && ax < 0.05 - (1.465 - z) * 0.6 && ax > 0.032 - (1.465 - z) * 0.6)
            return kit_trim;                                                        // (a V-neck's trim)
        if (col == 2 && y < 0.0 && z > 1.39 && ax < 0.005) return kit_trim;          // (a grandad's button opening)
        if (col == 3 && y < 0.0 && z > 1.40 && ax < 0.022 && ax > 0.012) return kit_trim;  // (a polo's placket)
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
    if (z < top && ax < 0.3735) return kit_trim;                                   // the sleeve's hem
    return head_colour(x, y, z, ax);
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
    vec2 uv = v_uv;
    if (crowd_amt > 0.0) {                  // each person (a cell of the crowd picture) bobs on his own
        vec2 cell = floor(v_uv * vec2(46.0, 22.0));
        float h = fract(sin(dot(cell, vec2(12.9898, 78.233))) * 43758.5453);
        float jump = max(0.0, sin(osg_FrameTime * (5.0 + 4.0 * h) + h * 6.283));
        uv.y -= crowd_amt * 0.0035 * (crowd_amt > 2.0 ? jump : sin(osg_FrameTime * (1.0 + h) + h * 6.283));
    }
    vec4 base = kit_on > 0.5 ? kit_colour() * p3d_ColorScale
                             : (texture(p3d_Texture0, uv) + p3d_TexAlphaOnly) * v_color * p3d_ColorScale;
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
    float flood = 1.0;
    if (night_on > 0.5) {
        vec2 out_by = max(abs(v_world.xy) - vec2(62.0, 42.0), vec2(0.0));
        flood = clamp(1.0 - length(out_by) / 14.0, 0.12, 1.0) * clamp(1.0 - (v_world.z - 4.0) / 30.0, 0.35, 1.0);
        sky *= mix(0.45, 1.0, flood);
    }
    vec3 light = p3d_LightModel.ambient.rgb * sky + p3d_LightSource[0].diffuse.rgb * lambert * sun_visible() * flood;
    if (detail_amt > 0.0)
        base.rgb *= mix(vec3(1.0), texture(p3d_Texture1, v_uv * detail_scale).rgb * 2.0, detail_amt);
    vec3 col = base.rgb * light;
    float fog = clamp(exp(-length(v_view) * p3d_Fog.density), 0.0, 1.0);
    o_color = vec4(mix(p3d_Fog.color.rgb, col, fog), base.a);
}
