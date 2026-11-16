#version 130
// The 3D view's lighting (broadcast3d/viewer.py light_up): one sun with a shadow map, plus sky light.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;
uniform mat4 trans_model_to_clip_of_suncam;    // (the sun camera's view: broadcast3d/sunshadow.py)

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
in vec2 p3d_MultiTexCoord1;

out vec4 v_shadow;
out vec3 v_normal;
out vec4 v_color;
out vec2 v_uv;
out vec2 v_uv1;
out vec3 v_view;
out vec3 v_world;
uniform float kit_on;
uniform vec2 cloth;             // (time, how much: his shirt rippling as he runs)
// The players' bodies are moved onto their skeletons here, on the graphics card, rather than by Panda3D on the
// processor each frame (broadcast3d/viewer.py: hardware skinning).  skin_on 1 on the players only.
uniform float skin_on;
uniform mat4 p3d_TransformTable[48];
in vec4 transform_weight;
in uvec4 transform_index;

void main() {
    vec4 pv = p3d_Vertex;
    vec3 nrm = p3d_Normal;
    if (skin_on > 0.5) {
        mat4 m = p3d_TransformTable[transform_index.x] * transform_weight.x
               + p3d_TransformTable[transform_index.y] * transform_weight.y
               + p3d_TransformTable[transform_index.z] * transform_weight.z
               + p3d_TransformTable[transform_index.w] * transform_weight.w;
        pv = m * pv;
        nrm = mat3(m) * nrm;
    }
    if (kit_on > 0.5 && kit_on < 1.5 && cloth.y > 0.0) {
        // A loose shirt moving as he runs: soft waves running up the cloth, most at the hem, none at the
        // shoulders (paint place: x across, y height).
        float pz = p3d_MultiTexCoord0.y, ax = abs(p3d_MultiTexCoord0.x);
        float w = smoothstep(1.32, 0.96, pz) * step(0.915, pz) * (1.0 - smoothstep(0.17, 0.22, ax));
        float wave = sin(cloth.x * 11.0 - pz * 38.0 + ax * 24.0) * 0.6 + sin(cloth.x * 7.0 + ax * 41.0) * 0.4;
        pv.xyz += nrm * (cloth.y * w * wave);
    }
    vec4 view = p3d_ModelViewMatrix * pv;
    v_view = view.xyz;
    v_world = (p3d_ModelMatrix * pv).xyz;
    v_shadow = trans_model_to_clip_of_suncam * pv;
    v_normal = p3d_NormalMatrix * nrm;
    v_color = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
    v_uv1 = p3d_MultiTexCoord1;
    gl_Position = p3d_ModelViewProjectionMatrix * pv;
}
