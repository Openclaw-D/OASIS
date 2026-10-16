// Architectural ink before DOF/TSR so temporal AA resolves fine facade edges.
// Values are HDR radiance under the fixed EV0 exposure, not display sRGB.
float2 uv = GetDefaultSceneTextureUV(Parameters, 14);
float2 pixel = View.BufferSizeAndInvSize.zw * LineWidth;
float3 color = SceneTextureLookup(uv, 14, false).rgb;
float depth = SceneTextureLookup(uv, 1, false).r;
float stencil = SceneTextureLookup(uv, 25, false).r;
float customDepth = SceneTextureLookup(uv, 13, false).r;
if (customDepth > depth + 10) stencil = 0;
float3 normal = normalize(SceneTextureLookup(uv, 8, false).xyz);
float raw = max(0, dot(color, float3(0.2126, 0.7152, 0.0722)));
float base = SceneTextureLookup(uv, 26, false).r;
float gray = base > 0.01 && base < 0.3 ? 0.06 + raw * 0.45 :
    raw > 0.025 ? lerp(0.8, 3.8, saturate(raw)) : raw;
if (stencil < 0.5) gray = 16.0;
float edge = 0;
float heroEdge = 0;
float2 offsets[4] = {float2(-1,0), float2(1,0), float2(0,-1), float2(0,1)};
[unroll] for (int i = 0; i < 4; ++i)
{
    float2 q = uv + pixel * offsets[i];
    float ns = SceneTextureLookup(q, 25, false).r;
    float nd = SceneTextureLookup(q, 1, false).r;
    if (SceneTextureLookup(q, 13, false).r > nd + 10) ns = 0;
    bool local = (stencil > 0.5 && stencil < 2.5) || (ns > 0.5 && ns < 2.5);
    float3 nn = normalize(SceneTextureLookup(q, 8, false).xyz);
    float silhouette = abs(stencil - ns) > 0.5 ? 1 : 0;
    float crease = (dot(normal, nn) < 0.70 && abs(depth - nd) / max(depth, 50) > 0.003) ? 1 : 0;
    float value = local ? max(silhouette, crease) : 0;
    edge = max(edge, value);
    heroEdge = max(heroEdge, value * ((abs(stencil - 1) < 0.1 || abs(ns - 1) < 0.1) ? 1 : 0));
}
gray = lerp(gray, heroEdge > 0.5 ? 0.003 : 0.04, edge);
return gray.xxx;
