"""Small geometry helpers for Panda3D: boxes, prisms, spheres, slopes - built in code (no model files)."""
import math
from panda3d.core import (GeomVertexFormat, GeomVertexData, GeomVertexWriter, GeomTriangles, Geom, GeomNode,
                          Vec3)

FMT = GeomVertexFormat.getV3n3c4t2()


class Mesh:
    def __init__(self, name="mesh"):
        self.vd = GeomVertexData(name, FMT, Geom.UHStatic)
        self.v = GeomVertexWriter(self.vd, "vertex"); self.n = GeomVertexWriter(self.vd, "normal")
        self.c = GeomVertexWriter(self.vd, "color"); self.t = GeomVertexWriter(self.vd, "texcoord")
        self.tri = GeomTriangles(Geom.UHStatic); self.i = 0; self.name = name

    def quad(self, a, b, c, d, col=(1, 1, 1, 1), uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        a, b, c, d = map(Vec3, (a, b, c, d))
        nrm = (b - a).cross(d - a); nrm.normalize()
        for p, t in zip((a, b, c, d), uv):
            self.v.addData3(p); self.n.addData3(nrm); self.c.addData4(*col); self.t.addData2(*t)
        self.tri.addVertices(self.i, self.i + 1, self.i + 2); self.tri.addVertices(self.i, self.i + 2, self.i + 3)
        self.i += 4

    def tri3(self, a, b, c, col=(1, 1, 1, 1)):
        a, b, c = map(Vec3, (a, b, c))
        nrm = (b - a).cross(c - a); nrm.normalize()
        for p, t in zip((a, b, c), ((0, 0), (1, 0), (0.5, 1))):
            self.v.addData3(p); self.n.addData3(nrm); self.c.addData4(*col); self.t.addData2(*t)
        self.tri.addVertices(self.i, self.i + 1, self.i + 2); self.i += 3

    def node(self):
        g = Geom(self.vd); g.addPrimitive(self.tri)
        gn = GeomNode(self.name); gn.addGeom(g)
        return gn


def box_into(m, x0, y0, z0, x1, y1, z1, col=(1, 1, 1, 1), uvs=1.0):
    """Axis-aligned box (all six faces, outward)."""
    U = ((0, 0), (uvs, 0), (uvs, uvs), (0, uvs))
    m.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), col, U)      # front (-y)
    m.quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), col, U)      # back
    m.quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), col, U)      # left
    m.quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), col, U)      # right
    m.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), col, U)      # top
    m.quad((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0), col, U)      # bottom


def box(parent, x0, y0, z0, x1, y1, z1, col=(1, 1, 1, 1), name="box"):
    m = Mesh(name); box_into(m, x0, y0, z0, x1, y1, z1, col)
    return parent.attachNewNode(m.node())


def sphere(parent, r, col=(1, 1, 1, 1), seg=10, ring=7, name="sphere", z_from=-1.0):
    m = Mesh(name)
    def P(i, j):
        th = math.pi * j / ring; ph = 2 * math.pi * i / seg
        return (r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), r * math.cos(th))
    for j in range(ring):
        if math.cos(math.pi * (j + 1) / ring) < z_from - 1e-6 and z_from > -1:
            continue
        for i in range(seg):
            a, b, c, d = P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)
            m.quad(d, c, b, a, col)
    return parent.attachNewNode(m.node())


def prism(parent, r, h, sides=10, col=(1, 1, 1, 1), taper=1.0, name="prism", uv_rep=(4, 8)):
    m = Mesh(name)
    for i in range(sides):
        a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
        p0 = (r * math.cos(a0), r * math.sin(a0)); p1 = (r * math.cos(a1), r * math.sin(a1))
        q0 = (p0[0] * taper, p0[1] * taper); q1 = (p1[0] * taper, p1[1] * taper)
        u0, u1 = uv_rep[0] * i / sides, uv_rep[0] * (i + 1) / sides
        m.quad((p0[0], p0[1], 0), (p1[0], p1[1], 0), (q1[0], q1[1], h), (q0[0], q0[1], h), col,
               ((u0, 0), (u1, 0), (u1, uv_rep[1]), (u0, uv_rep[1])))
    return parent.attachNewNode(m.node())
