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
uniform float mud_amt;                  // (a wet day: mud splashed up the boots, socks and the backs of the legs)
uniform vec4 kit_shirt, kit_trim, kit_shorts, kit_socks, kit_socktop, kit_skin, kit_hair, kit_gloves;
uniform vec4 kit_boots;                 // (rgb, a: 1 = a bright boot with a white sole)
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
    float beard = floor(kit_info.w / 8.0 + 0.01);                  // 0 clean-shaven, 1 stubble, 2 a full beard
    float style = kit_info.w - beard * 8.0;                        // 0 crop 1 buzz cut 2 longer 3 quiff 4 curls 5 bald
    bool is_long = (style > 1.5 && style < 2.5) || (style > 3.5 && style < 4.5) || style > 5.5;
    bool fade = (style > 0.5 && style < 1.5) || (style > 2.5 && style < 3.5);
    vec3 skin = kit_skin.rgb;
    // The hair close to the scalp (the cut's own volume is a mesh on top of this): a hairline that's high at
    // the front, down to above the ears at the sides and to the nape at the back - soft-edged, and fading
    // out lower down on the short-sided cuts.
    float back = is_long ? 1.55 : 1.605;
    float frontline = 1.735 - 0.018 * smoothstep(0.03, 0.065, ax);
    float l = y < -0.02 ? mix(1.672, frontline, smoothstep(-0.02, -0.08, y))
                        : mix(1.672, back, smoothstep(-0.02, 0.05, y));
    bool ear = ax > 0.064 && z > 1.612 && z < 1.676 && abs(y - 0.006) < 0.03;
    if (!ear) {
        float amt = (style > 4.5 && style < 5.5) ? 0.12 : (fade ? 0.55 : 1.0);
        if (fade) amt *= mix(0.4, 1.0, smoothstep(l, l + 0.07, z));
        skin = mix(skin, kit_hair.rgb, smoothstep(l - 0.004, l + 0.007, z) * amt);
    }
    if (y < -0.06 && z < l) {                                       // the face
        vec2 e = vec2(ax - 0.033, z - 1.6555);
        vec2 lid = vec2(e.x / 0.0098, e.y / 0.0051);
        float in_eye = dot(lid, lid);
        float r = length(e);
        if (in_eye < 1.0) {                                         // eyes: mostly iris, a little white, the
            if (r < 0.0017) return vec4(0.02, 0.02, 0.02, 1.0);     //  upper lid's shadow across the top
            vec3 c = r < 0.0041 ? vec3(0.17, 0.11, 0.07) : vec3(0.80, 0.78, 0.75);
            return vec4(c * (e.y > 0.0026 ? 0.6 : 1.0), 1.0);
        }
        if (in_eye < 1.5 && e.y > 0.0) return vec4(skin * 0.5, 1.0);            // the upper lid's line
        vec2 so = vec2(e.x / 0.017, e.y / 0.0105);
        skin *= mix(0.88, 1.0, smoothstep(0.6, 1.3, dot(so, so)));               // the eye socket's shade
        float bz = 1.6742 + 0.0022 * (1.0 - pow((ax - 0.034) / 0.021, 2.0));
        float bt = 0.0036 * (1.0 - 0.6 * smoothstep(0.022, 0.056, ax));             // (fuller at the inner end)
        if (ax > 0.010 && ax < 0.058) {                                          // brows: soft-edged, a little
            float hairs = 0.9 + 0.1 * sin(ax * 5200.0 + z * 3100.0);             //  uneven, like hairs, fading
            float a = smoothstep(bt, bt * 0.25, abs(z - bz)) * hairs                 //  in at the inner end and
                    * smoothstep(0.010, 0.017, ax) * smoothstep(0.058, 0.050, ax);   //  out at the outer
            skin = mix(skin, mix(kit_hair.rgb, kit_skin.rgb, 0.22), min(1.0, a * 1.1));
        }
        vec2 lp = vec2(ax / 0.021, (z - 1.588) / 0.0058);
        float in_lip = dot(lp, lp);
        if (in_lip < 1.0) {                                         // lips: a natural colour, a line between
            vec3 c = kit_skin.rgb * vec3(0.90, 0.72, 0.70);
            if (abs(z - 1.5883) < 0.0007) c = kit_skin.rgb * vec3(0.52, 0.4, 0.38);
            return vec4(mix(c, skin, smoothstep(0.7, 1.0, in_lip)), 1.0);
        }
    }
    if (beard > 0.5 && y < 0.01) {                                  // stubble or a beard: jaw, chin and top lip
        float top = 1.598 + 0.032 * smoothstep(0.02, 0.066, ax);
        float a = smoothstep(top, top - (beard > 1.5 ? 0.012 : 0.03), z) * smoothstep(1.528, 1.548, z);
        vec2 lp = vec2(ax / 0.024, (z - 1.588) / 0.0085);
        a *= smoothstep(1.0, 1.5, dot(lp, lp));
        float m = smoothstep(0.031, 0.02, ax) * smoothstep(1.609, 1.603, z) * smoothstep(1.593, 1.597, z);
        a = max(a, m) * smoothstep(0.01, -0.02, y);
        skin = mix(skin, mix(kit_hair.rgb, kit_skin.rgb, 0.15), a * (beard > 1.5 ? 0.85 : 0.3));
    }
    return vec4(skin, 1.0);
}

float vnoise(vec3 p) {                  // (smooth value noise, 0..1)
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n = 0.0;
    for (int k = 0; k < 8; k++) {
        vec3 o = vec3(float(k & 1), float((k >> 1) & 1), float((k >> 2) & 1));
        float h = fract(sin(dot(i + o, vec3(127.1, 311.7, 74.7))) * 43758.5453);
        vec3 w = mix(1.0 - f, f, o);
        n += h * w.x * w.y * w.z;
    }
    return n;
}

vec3 muddy(vec3 c, float x, float y, float z) {
    // Splashes: thick on the boots, up the socks and the backs of the calves, a few up the backs of the shorts.
    float up = smoothstep(0.62, 0.04, z) + 0.45 * smoothstep(0.0, 0.06, y) * smoothstep(0.98, 0.70, z) *
               step(0.62, z);
    float n = vnoise(vec3(x, y, z) * 55.0) * 0.6 + vnoise(vec3(x, y, z) * 140.0) * 0.4;
    float a = smoothstep(0.64, 0.80, n + up * 0.30 - 0.06) * mud_amt;
    return mix(c * (1.0 - 0.08 * mud_amt), vec3(0.27, 0.21, 0.14), a * 0.85);
}

float shirt_folds(float x, float y, float z, float ax) {
    // Soft folds in a loose shirt: creases running from the armpits down and in across the chest and back,
    // and the cloth gathering in soft ripples above the hem.  (Shading only - a few percent darker in the
    // hollows.)
    if (ax > 0.24) return 1.0;
    float f = 0.0;
    float d = (ax - 0.17) + (z - 1.30) * 0.8;                         // (diagonal, from the armpit)
    f += smoothstep(1.32, 1.18, z) * smoothstep(0.92, 1.05, z) * smoothstep(0.24, 0.12, ax)
         * (0.5 + 0.5 * sin(d * 95.0 + (y < 0.0 ? 0.0 : 1.7)));
    float hem = smoothstep(1.04, 0.95, z) * smoothstep(0.90, 0.95, z);
    f += hem * (0.5 + 0.5 * sin(x * 70.0 + (y < 0.0 ? 0.5 : 2.1) + 6.0 * sin(z * 40.0)));
    f *= 0.4 + 0.9 * vnoise(vec3(x, y, z) * 18.0);                    // (uneven: cloth isn't regular)
    return 1.0 - 0.055 * f;
}

vec4 kit_colour() {
    float x = v_uv.x, z = v_uv.y, y = v_uv1.x, ax = abs(x);
    bool keeper = kit_info.y > 0.5;
    if (z < 0.10 || (z < 0.13 && v_uv1.x < -0.03)) {                                // boots: his own colour,
        if (z < 0.017) return kit_boots.a > 0.5 ? vec4(0.93, 0.93, 0.93, 1.0) : vec4(0.2, 0.2, 0.21, 1.0);   // a sole,
        if (y < -0.02 && y > -0.12 && abs(ax - 0.19) < 0.012 && z > 0.035) return vec4(kit_boots.rgb * 0.55 + 0.25, 1.0);  // laces
        return vec4(kit_boots.rgb, 1.0);
    }
    if (kit_extra.y > 0.5 && z < 0.927 && ax < 0.25) return kit_shorts;             // (trousers: the managers)
    if (kit_extra.w > 0.5 && z < 1.49 && ax >= 0.76) return kit_gloves;             // (gloves on a cold day)
    if (kit_extra.z > 0.5 && z < 1.49 && ax > 0.24 && ax < 0.76 && !(z > 1.43 && ax < 0.09)) {
        if (kit_extra.y > 0.5) return kit_shirt;                                    // (a coat / training top)
        return ax > 0.73 ? kit_trim : vec4(shirt_at(x, y, z, false), 1.0);         // (long sleeves, cuffed)
    }
    if (z < 0.40) return kit_socks;
    if (z < 0.46) return kit_socktop;
    if (z < 0.619) return kit_skin;
    if (z < 0.927 && ax < 0.25) {                                                   // shorts, a stripe down the side
        float c = 0.084 + (0.955 - z) / 0.333 * 0.028;
        float dx = ax - c;
        return (dx > 0.03 && abs(y + 0.002) < 0.017) ? kit_trim : kit_shorts;      // (3.5 cm wide, at the side)
    }
    float top = 1.49 + 0.045 * smoothstep(0.1, 0.2, ax);                            // (the shoulders)
    // The neckline goes round the base of the neck: low at the front (the throat), up the sides over the
    // traps and higher at the back - not a flat line across.  The collar is a band just below it.
    float ny = y + 0.012;
    float rn = length(vec2(x, ny));
    float front = clamp(-ny / max(rn, 1e-4), 0.0, 1.0);
    float neck = mix(1.512, 1.478, pow(front, 1.4));
    float near_neck = 1.0 - smoothstep(0.075, 0.13, rn);
    top = mix(top, neck + 0.35 * max(0.0, rn - 0.065), near_neck);
    if (z < top && ax < 0.355) {
        int col = int(kit_extra.x + 0.5);
        float band = col == 3 ? 0.045 : (col == 2 ? 0.035 : 0.022);                 // the collar (a polo's is deeper)
        band *= mix(0.45, 1.0, front);                                              // (over the traps: thinner)
        float reach = col == 3 ? 0.105 : 0.092;
        band *= 1.0 - smoothstep(reach - 0.02, reach, rn);
        if (z > top - band) return kit_trim;
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
        return vec4(shirt_at(x, y, z, ax < 0.24) * shirt_folds(x, y, z, ax), 1.0);
    }
    if (keeper && z < 1.49 && ax < 0.76) return vec4(shirt_at(x, y, z, false), 1.0);   // a keeper's long sleeves
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
    vec4 base = kit_on > 1.5 ? vec4(kit_hair.rgb * (0.8 + 0.3 * smoothstep(1.68, 1.80, v_uv.y)), 1.0) * p3d_ColorScale
              : kit_on > 0.5 ? vec4(mud_amt > 0.0 && v_uv.y < 1.0 ? muddy(kit_colour().rgb, v_uv.x, v_uv1.x, v_uv.y)
                                                                    : kit_colour().rgb, 1.0) * p3d_ColorScale
                             : (texture(p3d_Texture0, uv) + p3d_TexAlphaOnly) * v_color * p3d_ColorScale;
    float nl = length(v_normal);
    float lambert = 1.0;
    if (nl > 0.01) {
        vec3 n = v_normal / nl;
        if (!gl_FrontFacing) n = -n;
        float d = dot(n, normalize(p3d_LightSource[0].position.xyz));
        // On the players, light that wraps a little round the form (skin and cloth both scatter it): softer
        // shading from lit to shadow instead of a hard line.
        lambert = kit_on > 0.5 ? max((d + 0.3) / 1.3, 0.0) : max(d, 0.0);
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
    if (kit_on > 0.5 && kit_on < 1.5 && nl > 0.01) {
        // a soft rim of sky light on the edges facing away from the camera (as a TV camera sees players)
        vec3 n3 = v_normal / nl;
        if (!gl_FrontFacing) n3 = -n3;
        float rim = pow(1.0 - abs(dot(n3, normalize(-v_view))), 3.0);
        col += base.rgb * p3d_LightModel.ambient.rgb * rim * 0.35;
    }
    float fog = clamp(exp(-length(v_view) * p3d_Fog.density), 0.0, 1.0);
    o_color = vec4(mix(p3d_Fog.color.rgb, col, fog), base.a);
}
