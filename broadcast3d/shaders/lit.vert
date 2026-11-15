#version 130
// The 3D view's lighting (broadcast3d/viewer.py light_up): one sun with a shadow map, plus sky light.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;
uniform struct p3d_LightSourceParameters {
    vec4 position;
    vec4 diffuse;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];

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

void main() {
    vec4 view = p3d_ModelViewMatrix * p3d_Vertex;
    v_view = view.xyz;
    v_world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_shadow = p3d_LightSource[0].shadowViewMatrix * view;
    v_normal = p3d_NormalMatrix * p3d_Normal;
    v_color = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
    v_uv1 = p3d_MultiTexCoord1;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
