/* The mesh decimator's core (decimate.py builds it and calls ttt2_decimate through ctypes; read its docstring
 * first: it says what the arrays hold and why the rules are what they are).
 *
 * Half-edge collapses (a vertex U moves onto a neighbour V and disappears; V keeps its position and attributes)
 * in order of their quadric error (Garland and Heckbert 1997: each vertex sums the squared distances to the planes
 * of the triangles it had, area-weighted), plus:
 * - feature edges: open boundaries (one triangle), seams (the two triangles use different wedges at an end: UV or
 *   normal seams, material borders) get a plane through the edge across the surface in the quadric, and their
 *   vertices only move along them; a vertex with other than two feature edges, at a sharp feature corner, on a
 *   non-manifold edge or where fans meet in a point is locked;
 * - wedges: a position vertex has one wedge per distinct attribute set (decimate.py makes them); each wedge of U
 *   must map to exactly one wedge of V through the triangles that hold both, so a seam's two sides move together;
 * - attribute error: each wedge sums, per triangle, the squared error of the triangle's linear attribute field
 *   (Garland and Heckbert 1998), evaluated at V's position and V's attributes;
 * - skin: the squared difference of U's and V's skin weights times U's area; the whole cost times U's factor
 *   (pfactor: decimate.py's scale correction);
 * - quotas: a point with a wedge in a part (wpart) that has no more than its quota of live wedges stays;
 * - the link condition (no non-manifold results) and, on every triangle that changes, a test of its face normal
 *   (no flips, no turning to the other side of its corners' normals) and of its corners' normals (none may come
 *   to point apart, as across a fold whose rounding went).
 * Written for this project (no third-party code).
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define INF 8                   /* skin influences per wedge */
#define MAXK 8                  /* attribute channels at most */
#define MAXC 512                /* triangles / neighbours around one vertex the scratch arrays hold */

/* params[] indices */
enum { P_FEATURE, P_FLIP, P_CORNER, P_SKIN, P_REG, P_MAXCOST, P_NORMAL, P_COUNT };
/* stats[] indices */
enum { S_COLLAPSES, S_LASTCOST, S_LOCKED, S_FEATURE, S_NONMANIFOLD, S_COUNT };

typedef struct {
    int npos, nw, ntri, k, aq;
    const double *pos, *attr, *sw, *pfactor, *wnrm;
    const int *wpos, *sj, *wpart;
    const long *quota;
    int *tri;
    double *q, *aqd, *warea;
    int *wref;
    long live, *plive;
    unsigned char *lock, *dead, *tdead;
    int *fcount, *fnb;
    int *ts, *tn, *tc, *pool;
    long pool_n, pool_cap;
    int *mark, stamp;
    int *version, *target;
    double *hc;
    int *hv, *hver;
    long hn, hcap;
    double feature_w, flip_cos, corner_cos, skin_w, reg, maxcost, normal_cos;
} D;

/* ------------------------------------------------------------------------------------------------ quadrics */
static void q_plane(double *q, const double *n, double d, double w)
{
    q[0] += w * n[0] * n[0]; q[1] += w * n[0] * n[1]; q[2] += w * n[0] * n[2]; q[3] += w * n[0] * d;
    q[4] += w * n[1] * n[1]; q[5] += w * n[1] * n[2]; q[6] += w * n[1] * d;
    q[7] += w * n[2] * n[2]; q[8] += w * n[2] * d; q[9] += w * d * d;
}

static double q_eval(const double *q, const double *p)
{
    double x = p[0], y = p[1], z = p[2];
    return q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + 2 * q[3] * x + q[4] * y * y + 2 * q[5] * y * z +
           2 * q[6] * y + q[7] * z * z + 2 * q[8] * z + q[9];
}

/* attribute quadric, 11 + 4k doubles: A (xx xy xz yy yz zz), b (3), E, W, per channel G (3) and D:
 * error(p, a) = p'Ap + 2b.p + E - 2 sum_c a_c (G_c.p + D_c) + W sum_c a_c^2 */
static double aq_eval(const D *d, const double *q, const double *p, const double *a)
{
    double x = p[0], y = p[1], z = p[2];
    double e = q[0] * x * x + 2 * q[1] * x * y + 2 * q[2] * x * z + q[3] * y * y + 2 * q[4] * y * z + q[5] * z * z +
               2 * (q[6] * x + q[7] * y + q[8] * z) + q[9];
    for (int c = 0; c < d->k; c++) {
        const double *g = q + 11 + 4 * c;
        e += -2 * a[c] * (g[0] * x + g[1] * y + g[2] * z + g[3]) + q[10] * a[c] * a[c];
    }
    return e > 0 ? e : 0;
}

static void cross(const double *a, const double *b, double *o)
{
    o[0] = a[1] * b[2] - a[2] * b[1];
    o[1] = a[2] * b[0] - a[0] * b[2];
    o[2] = a[0] * b[1] - a[1] * b[0];
}

static double dot(const double *a, const double *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static void sub(const double *a, const double *b, double *o)
{
    o[0] = a[0] - b[0]; o[1] = a[1] - b[1]; o[2] = a[2] - b[2];
}

/* ------------------------------------------------------------------------------------- triangle lists */
static int grow(D *d, int v)
{
    int cap = d->tc[v] ? 2 * d->tc[v] : 8;
    if (d->pool_n + cap > d->pool_cap) {
        long nc = (d->pool_n + cap) * 2;
        int *np = realloc(d->pool, nc * sizeof(int));
        if (!np)
            return -1;
        d->pool = np;
        d->pool_cap = nc;
    }
    memcpy(d->pool + d->pool_n, d->pool + d->ts[v], d->tn[v] * sizeof(int));
    d->ts[v] = (int)d->pool_n;
    d->tc[v] = cap;
    d->pool_n += cap;
    return 0;
}

static int add_tri(D *d, int v, int t)
{
    if (d->tn[v] == d->tc[v] && grow(d, v))
        return -1;
    d->pool[d->ts[v] + d->tn[v]++] = t;
    return 0;
}

/* the live triangles of v (its list compacted in place) */
static int *tris_of(D *d, int v, int *n)
{
    int *l = d->pool + d->ts[v], m = 0;
    for (int i = 0; i < d->tn[v]; i++)
        if (!d->tdead[l[i]])
            l[m++] = l[i];
    d->tn[v] = m;
    *n = m;
    return l;
}

static int pos_of(const D *d, int t, int c) { return d->wpos[d->tri[3 * t + c]]; }

/* the corner of t at position vertex v, or -1 */
static int corner(const D *d, int t, int v)
{
    for (int c = 0; c < 3; c++)
        if (pos_of(d, t, c) == v)
            return c;
    return -1;
}

static void wref_add(D *d, int w, int k)
{
    int before = d->wref[w];
    d->wref[w] += k;
    if (before > 0 && d->wref[w] == 0) {
        d->live--;
        d->plive[d->wpart[w]]--;
    } else if (before == 0 && d->wref[w] > 0) {
        d->live++;
        d->plive[d->wpart[w]]++;
    }
}

/* ------------------------------------------------------------------------------------------------ heap */
static int push(D *d, double c, int v, int ver)
{
    if (d->hn == d->hcap) {
        long nc = d->hcap * 2 + 1024;
        double *a = realloc(d->hc, nc * sizeof(double));
        if (!a)
            return -1;
        d->hc = a;
        int *b = realloc(d->hv, nc * sizeof(int));
        if (!b)
            return -1;
        d->hv = b;
        b = realloc(d->hver, nc * sizeof(int));
        if (!b)
            return -1;
        d->hver = b;
        d->hcap = nc;
    }
    long i = d->hn++;
    while (i > 0) {
        long p = (i - 1) / 2;
        if (d->hc[p] <= c)
            break;
        d->hc[i] = d->hc[p]; d->hv[i] = d->hv[p]; d->hver[i] = d->hver[p];
        i = p;
    }
    d->hc[i] = c; d->hv[i] = v; d->hver[i] = ver;
    return 0;
}

static void pop(D *d, double *c, int *v, int *ver)
{
    *c = d->hc[0]; *v = d->hv[0]; *ver = d->hver[0];
    double lc = d->hc[--d->hn];
    int lv = d->hv[d->hn], lver = d->hver[d->hn];
    long i = 0;
    for (;;) {
        long a = 2 * i + 1, b = a + 1, m = i;
        double mc = lc;
        if (a < d->hn && d->hc[a] < mc) { m = a; mc = d->hc[a]; }
        if (b < d->hn && d->hc[b] < mc) { m = b; }
        if (m == i)
            break;
        d->hc[i] = d->hc[m]; d->hv[i] = d->hv[m]; d->hver[i] = d->hver[m];
        i = m;
    }
    if (d->hn > 0) {
        d->hc[i] = lc; d->hv[i] = lv; d->hver[i] = lver;
    }
}

/* ------------------------------------------------------------------------------------------- collapses */
/* U's wedges and the V wedge each one goes to (through the triangles holding both): the count, or -1 when a wedge
 * of U has none or two (the collapse would tear or move a seam) */
static int wedge_map(D *d, int u, int v, int *uw, int *vw)
{
    int n, m = 0, *l = tris_of(d, u, &n);
    for (int i = 0; i < n; i++) {
        int cv = corner(d, l[i], v);
        if (cv < 0)
            continue;
        int a = d->tri[3 * l[i] + corner(d, l[i], u)], b = d->tri[3 * l[i] + cv], j;
        for (j = 0; j < m && uw[j] != a; j++)
            ;
        if (j < m) {
            if (vw[j] != b)
                return -1;
        } else {
            if (m == MAXC)
                return -1;
            uw[m] = a; vw[m] = b; m++;
        }
    }
    if (!m)
        return -1;
    for (int i = 0; i < n; i++) {
        int a = d->tri[3 * l[i] + corner(d, l[i], u)], j;
        for (j = 0; j < m && uw[j] != a; j++)
            ;
        if (j == m)
            return -1;
    }
    return m;
}

static double skin_dist(const D *d, int a, int b)
{
    const int *ja = d->sj + INF * a, *jb = d->sj + INF * b;
    const double *wa = d->sw + INF * a, *wb = d->sw + INF * b;
    double s = 0;
    for (int i = 0; i < INF; i++) {
        if (wa[i] <= 0)
            continue;
        double o = 0;
        for (int j = 0; j < INF; j++)
            if (wb[j] > 0 && jb[j] == ja[i])
                o += wb[j];
        s += (wa[i] - o) * (wa[i] - o);
    }
    for (int j = 0; j < INF; j++) {
        if (wb[j] <= 0)
            continue;
        int found = 0;
        for (int i = 0; i < INF; i++)
            if (wa[i] > 0 && ja[i] == jb[j])
                found = 1;
        if (!found)
            s += wb[j] * wb[j];
    }
    return s;
}

static double cost(D *d, int u, int v, const int *uw, const int *vw, int m)
{
    const double *pu = d->pos + 3 * u, *pv = d->pos + 3 * v;
    double e = q_eval(d->q + 10 * u, pv), area = 0;
    for (int i = 0; i < m; i++) {
        e += aq_eval(d, d->aqd + (long)d->aq * uw[i], pv, d->attr + (long)d->k * vw[i]);
        e += d->skin_w * d->warea[uw[i]] * skin_dist(d, uw[i], vw[i]);
        area += d->warea[uw[i]];
    }
    double t[3];
    sub(pu, pv, t);
    e += d->reg * area * dot(t, t);
    return e * d->pfactor[u];
}

static double ndot(const D *d, int a, int b)
{
    return dot(d->wnrm + 3 * a, d->wnrm + 3 * b);
}

/* the smaller cosine between corner c's normal (as wedge w) and the other two corners' of triangle t */
static double spread(const D *d, int t, int c, int w)
{
    const int *x = d->tri + 3 * t;
    double a = ndot(d, w, x[(c + 1) % 3]), b = ndot(d, w, x[(c + 2) % 3]);
    return a < b ? a : b;
}

/* the link condition, the feature rules, the flip test and the normal test for U -> V */
static int valid(D *d, int u, int v)
{
    if (d->fcount[u] == 2) {
        int *f = d->fnb + 2 * u;
        if (f[0] != v && f[1] != v)
            return 0;
        if (d->fcount[v] == 2) {             /* a feature loop of three vertices cannot lose one */
            int w = f[0] == v ? f[1] : f[0], *g = d->fnb + 2 * v;
            if ((g[0] == u ? g[1] : g[0]) == w)
                return 0;
        }
    }
    int nu, nv, *lu = tris_of(d, u, &nu), *lv = tris_of(d, v, &nv);
    int s = d->stamp += 2;
    int apex[2], na = 0;
    for (int i = 0; i < nu; i++)
        for (int c = 0; c < 3; c++)
            d->mark[pos_of(d, lu[i], c)] = s;
    int common = 0;
    for (int i = 0; i < nv; i++)
        for (int c = 0; c < 3; c++) {
            int x = pos_of(d, lv[i], c);
            if (x == u || x == v)
                continue;
            if (d->mark[x] == s) {
                common++;
                d->mark[x] = s + 1;
            }
        }
    for (int i = 0; i < nu; i++) {
        int t = lu[i];
        if (corner(d, t, v) < 0)
            continue;
        int x = -1;
        for (int c = 0; c < 3; c++)
            if (pos_of(d, t, c) != u && pos_of(d, t, c) != v)
                x = pos_of(d, t, c);
        if ((na > 0 && apex[0] == x) || (na > 1 && apex[1] == x))
            continue;
        if (na == 2)
            return 0;                        /* a non-manifold edge */
        apex[na++] = x;
    }
    if (common != na)
        return 0;
    static __thread int uw[MAXC], vw[MAXC];
    int m = wedge_map(d, u, v, uw, vw);
    if (m < 0)
        return 0;
    const double *pv = d->pos + 3 * v;
    for (int i = 0; i < nu; i++) {
        int t = lu[i];
        if (corner(d, t, v) >= 0)
            continue;
        const double *p[3], *q[3];
        for (int c = 0; c < 3; c++) {
            int x = pos_of(d, t, c);
            p[c] = d->pos + 3 * x;
            q[c] = x == u ? pv : p[c];
        }
        double e1[3], e2[3], n0[3], n1[3];
        sub(p[1], p[0], e1); sub(p[2], p[0], e2); cross(e1, e2, n0);
        sub(q[1], q[0], e1); sub(q[2], q[0], e2); cross(e1, e2, n1);
        double a0 = dot(n0, n0), a1 = dot(n1, n1);
        if (a1 <= 1e-12 * a0 || a1 <= 1e-30)
            return 0;
        if (dot(n0, n1) <= d->flip_cos * sqrt(a0 * a1))
            return 0;
        /* no triangle may get corners whose normals point apart (a fold's rounding gone: a dark streak) */
        int c = corner(d, t, u), w = d->tri[3 * t + c], j;
        for (j = 0; j < m && uw[j] != w; j++)
            ;
        double after = spread(d, t, c, vw[j]);
        if (after < d->normal_cos && after < spread(d, t, c, w))
            return 0;
        /* nor turn to the other side of its corners' normals (either winding may be the front one) */
        const int *x = d->tri + 3 * t;
        double s0 = 0, s1 = 0;
        for (int k = 0; k < 3; k++) {
            s0 += dot(n0, d->wnrm + 3 * (k == c ? w : x[k]));
            s1 += dot(n1, d->wnrm + 3 * (k == c ? vw[j] : x[k]));
        }
        if ((s0 > 0) != (s1 > 0))
            return 0;
    }
    return 1;
}

/* may U still go: has every part its wedges are in more than its quota left? */
static int above_quota(D *d, int u)
{
    int n, *l = tris_of(d, u, &n);
    for (int i = 0; i < n; i++) {
        int w = d->tri[3 * l[i] + corner(d, l[i], u)];
        if (d->plive[d->wpart[w]] <= d->quota[d->wpart[w]])
            return 0;
    }
    return 1;
}

/* U's cheapest valid collapse goes on the heap (or none) */
static int best(D *d, int u)
{
    d->version[u]++;
    d->target[u] = -1;
    if (d->dead[u] || d->lock[u])
        return 0;
    int n, *l = tris_of(d, u, &n);
    if (!n || n > MAXC / 2 || !above_quota(d, u))   /* (a vertex with hundreds of triangles stays) */
        return 0;
    static __thread int nb[MAXC], uw[MAXC], vw[MAXC];
    static __thread double nc[MAXC];
    int m = 0, s = d->stamp += 2;
    d->mark[u] = s;
    for (int i = 0; i < n; i++)
        for (int c = 0; c < 3; c++) {
            int x = pos_of(d, l[i], c);
            if (d->mark[x] == s || m == MAXC)
                continue;
            d->mark[x] = s;
            if (d->fcount[u] == 2 && d->fnb[2 * u] != x && d->fnb[2 * u + 1] != x)
                continue;
            int k = wedge_map(d, u, x, uw, vw);
            if (k < 0)
                continue;
            double c0 = cost(d, u, x, uw, vw, k);
            int j = m++;
            while (j > 0 && nc[j - 1] > c0) {
                nc[j] = nc[j - 1]; nb[j] = nb[j - 1];
                j--;
            }
            nc[j] = c0; nb[j] = x;
        }
    for (int i = 0; i < m; i++)
        if (nc[i] <= d->maxcost && valid(d, u, nb[i])) {
            d->target[u] = nb[i];
            return push(d, nc[i], u, d->version[u]);
        }
    return 0;
}

static int collapse(D *d, int u, int v)
{
    static __thread int uw[MAXC], vw[MAXC], own[MAXC];
    int m = wedge_map(d, u, v, uw, vw);
    if (m < 0)
        return 0;
    int n, *l = tris_of(d, u, &n);
    if (n > MAXC)
        return 0;
    memcpy(own, l, n * sizeof(int));         /* (add_tri may move the pool) */
    l = own;
    for (int i = 0; i < n; i++) {
        int t = l[i], *w = d->tri + 3 * t;
        if (corner(d, t, v) >= 0) {
            d->tdead[t] = 1;
            for (int c = 0; c < 3; c++)
                wref_add(d, w[c], -1);
            continue;
        }
        int c = corner(d, t, u), j;
        for (j = 0; j < m && uw[j] != w[c]; j++)
            ;
        wref_add(d, vw[j], 1);
        wref_add(d, w[c], -1);
        w[c] = vw[j];
        if (add_tri(d, v, t))
            return -1;
    }
    for (int i = 0; i < m; i++) {
        double *a = d->aqd + (long)d->aq * vw[i], *b = d->aqd + (long)d->aq * uw[i];
        for (int j = 0; j < d->aq; j++)
            a[j] += b[j];
        d->warea[vw[i]] += d->warea[uw[i]];
    }
    for (int j = 0; j < 10; j++)
        d->q[10 * v + j] += d->q[10 * u + j];
    d->dead[u] = 1;
    d->tn[u] = 0;
    if (d->fcount[u] == 2) {                 /* the feature curve skips U */
        int *f = d->fnb + 2 * u, w = f[0] == v ? f[1] : f[0];
        if (d->fcount[v] == 2)
            d->fnb[2 * v + (d->fnb[2 * v] == u ? 0 : 1)] = w;
        if (d->fcount[w] == 2)
            d->fnb[2 * w + (d->fnb[2 * w] == u ? 0 : 1)] = v;
    }
    /* V and every vertex round it: their collapses changed */
    static __thread int ring[MAXC];
    int r = 0, s = d->stamp += 2;
    l = tris_of(d, v, &n);
    for (int i = 0; i < n; i++)
        for (int c = 0; c < 3; c++) {
            int x = pos_of(d, l[i], c);
            if (d->mark[x] != s && r < MAXC) {
                d->mark[x] = s;
                ring[r++] = x;
            }
        }
    for (int i = 0; i < r; i++)
        if (best(d, ring[i]))
            return -1;
    return 1;
}

/* ---------------------------------------------------------------------------------------------- set-up */
typedef struct { int a, b, t, c; } Edge;

static int edge_cmp(const void *x, const void *y)
{
    const Edge *e = x, *f = y;
    if (e->a != f->a)
        return e->a < f->a ? -1 : 1;
    if (e->b != f->b)
        return e->b < f->b ? -1 : 1;
    return 0;
}

static void feature(D *d, int a, int b)
{
    int ends[2] = {a, b};
    for (int i = 0; i < 2; i++) {
        int x = ends[i], y = ends[1 - i];
        if (d->fcount[x] < 2)
            d->fnb[2 * x + d->fcount[x]] = y;
        d->fcount[x]++;
    }
}

/* the plane through edge (a, b) across triangle t, into both ends' quadrics */
static void feature_plane(D *d, int t, int a, int b)
{
    const double *p0 = d->pos + 3 * pos_of(d, t, 0), *p1 = d->pos + 3 * pos_of(d, t, 1),
                 *p2 = d->pos + 3 * pos_of(d, t, 2), *pa = d->pos + 3 * a, *pb = d->pos + 3 * b;
    double e1[3], e2[3], n[3], e[3], m[3];
    sub(p1, p0, e1); sub(p2, p0, e2); cross(e1, e2, n);
    sub(pb, pa, e);
    cross(e, n, m);
    double len = sqrt(dot(m, m)), el = dot(e, e);
    if (len <= 1e-30)
        return;
    for (int c = 0; c < 3; c++)
        m[c] /= len;
    double off = -dot(m, pa);
    q_plane(d->q + 10 * a, m, off, d->feature_w * el);
    q_plane(d->q + 10 * b, m, off, d->feature_w * el);
}

/* do the triangles round v form one fan (joined through edges at v)? */
static int one_fan(D *d, int v)
{
    int n, *l = tris_of(d, v, &n);
    if (n > MAXC)
        return 0;
    static __thread int grp[MAXC];
    for (int i = 0; i < n; i++)
        grp[i] = i;
    for (int changed = 1; changed;) {
        changed = 0;
        for (int i = 0; i < n; i++)
            for (int j = i + 1; j < n; j++) {
                if (grp[i] == grp[j])
                    continue;
                int shared = 0;
                for (int a = 0; a < 3; a++) {
                    int x = pos_of(d, l[i], a);
                    if (x == v)
                        continue;
                    for (int b = 0; b < 3; b++)
                        if (pos_of(d, l[j], b) == x)
                            shared = 1;
                }
                if (shared) {
                    int g = grp[i] < grp[j] ? grp[i] : grp[j];
                    grp[i] = grp[j] = g;
                    changed = 1;
                }
            }
    }
    for (int i = 0; i < n; i++)
        if (grp[i] != grp[0])
            return 0;
    return 1;
}

static int setup(D *d, const unsigned char *lock_in, double *stats)
{
    int np = d->npos, nt = d->ntri;
    for (int v = 0; v < np; v++)
        d->dead[v] = 1;
    for (int t = 0; t < nt; t++)
        for (int c = 0; c < 3; c++) {
            int v = pos_of(d, t, c);
            d->dead[v] = 0;
            if (add_tri(d, v, t))
                return -1;
            wref_add(d, d->tri[3 * t + c], 1);
        }
    /* triangle planes and attribute fields */
    for (int t = 0; t < nt; t++) {
        const int *w = d->tri + 3 * t;
        const double *p0 = d->pos + 3 * d->wpos[w[0]], *p1 = d->pos + 3 * d->wpos[w[1]],
                     *p2 = d->pos + 3 * d->wpos[w[2]];
        double e1[3], e2[3], n[3];
        sub(p1, p0, e1); sub(p2, p0, e2); cross(e1, e2, n);
        double nn = dot(n, n);
        if (nn <= 1e-30)
            continue;
        double len = sqrt(nn), area = 0.5 * len, un[3] = {n[0] / len, n[1] / len, n[2] / len};
        for (int c = 0; c < 3; c++) {
            q_plane(d->q + 10 * d->wpos[w[c]], un, -dot(un, p0), area);
            d->warea[w[c]] += area;
        }
        double g1[3], g2[3];                 /* gradient basis: g = (da1 (e2 x n) + da2 (n x e1)) / |n|^2 */
        cross(e2, n, g1);
        cross(n, e1, g2);
        double q[11 + 4 * MAXK];
        memset(q, 0, sizeof(q));
        for (int c = 0; c < d->k; c++) {
            double a0 = d->attr[(long)d->k * w[0] + c], a1 = d->attr[(long)d->k * w[1] + c],
                   a2 = d->attr[(long)d->k * w[2] + c], g[3];
            for (int i = 0; i < 3; i++)
                g[i] = ((a1 - a0) * g1[i] + (a2 - a0) * g2[i]) / nn;
            double off = a0 - dot(g, p0);
            q[0] += area * g[0] * g[0]; q[1] += area * g[0] * g[1]; q[2] += area * g[0] * g[2];
            q[3] += area * g[1] * g[1]; q[4] += area * g[1] * g[2]; q[5] += area * g[2] * g[2];
            q[6] += area * off * g[0]; q[7] += area * off * g[1]; q[8] += area * off * g[2];
            q[9] += area * off * off;
            double *gc = q + 11 + 4 * c;
            gc[0] = area * g[0]; gc[1] = area * g[1]; gc[2] = area * g[2]; gc[3] = area * off;
        }
        q[10] = area;
        for (int c = 0; c < 3; c++) {
            double *a = d->aqd + (long)d->aq * w[c];
            for (int j = 0; j < d->aq; j++)
                a[j] += q[j];
        }
    }
    /* edges: boundaries, seams, non-manifold */
    Edge *e = malloc((size_t)nt * 3 * sizeof(Edge));
    if (!e)
        return -1;
    for (int t = 0; t < nt; t++)
        for (int c = 0; c < 3; c++) {
            int a = pos_of(d, t, c), b = pos_of(d, t, (c + 1) % 3);
            Edge *x = e + 3 * t + c;
            x->a = a < b ? a : b; x->b = a < b ? b : a; x->t = t; x->c = c;
        }
    qsort(e, (size_t)nt * 3, sizeof(Edge), edge_cmp);
    long ne = (long)nt * 3;
    for (long i = 0; i < ne;) {
        long j = i;
        while (j < ne && e[j].a == e[i].a && e[j].b == e[i].b)
            j++;
        int a = e[i].a, b = e[i].b;
        if (j - i == 1) {
            feature(d, a, b);
            feature_plane(d, e[i].t, a, b);
        } else if (j - i == 2) {
            int t1 = e[i].t, t2 = e[i + 1].t;
            int same = d->tri[3 * t1 + corner(d, t1, a)] == d->tri[3 * t2 + corner(d, t2, a)] &&
                       d->tri[3 * t1 + corner(d, t1, b)] == d->tri[3 * t2 + corner(d, t2, b)];
            /* the two triangles must run along the edge in opposite directions (consistent winding) */
            int dir1 = pos_of(d, t1, e[i].c) == a, dir2 = pos_of(d, t2, e[i + 1].c) == a;
            if (!same || dir1 == dir2) {
                feature(d, a, b);
                feature_plane(d, t1, a, b);
                feature_plane(d, t2, a, b);
            }
        } else {
            d->lock[a] = d->lock[b] = 1;
            stats[S_NONMANIFOLD] += 1;
        }
        i = j;
    }
    free(e);
    for (int v = 0; v < np; v++) {
        if (d->dead[v])
            continue;
        if (lock_in && lock_in[v])
            d->lock[v] = 1;
        if (d->fcount[v] && d->fcount[v] != 2)
            d->lock[v] = 1;
        if (d->fcount[v] == 2) {
            stats[S_FEATURE] += 1;
            double a[3], b[3];
            sub(d->pos + 3 * d->fnb[2 * v], d->pos + 3 * v, a);
            sub(d->pos + 3 * d->fnb[2 * v + 1], d->pos + 3 * v, b);
            double la = sqrt(dot(a, a)), lb = sqrt(dot(b, b));
            if (la <= 0 || lb <= 0 || dot(a, b) > d->corner_cos * la * lb)
                d->lock[v] = 1;          /* a corner: the feature turns sharply here */
        }
        if (!d->lock[v] && !one_fan(d, v))
            d->lock[v] = 1;
        if (d->lock[v])
            stats[S_LOCKED] += 1;
    }
    return 0;
}

/* ------------------------------------------------------------------------------------------------- entry */
/* Collapses until the live wedges (those some triangle uses) are at most `target` or nothing valid is left; a
 * point whose wedges are in a part (wpart) with no more than its quota live does not go.
 * pos (npos, 3); wpos (nw): each wedge's position vertex; attr (nw, k) weighted attributes; sj, sw (nw, 8) skin;
 * wnrm (nw, 3) unit normals; pfactor (npos) cost factors; lock_in (npos) or NULL; tri (ntri, 3) wedges, rewritten
 * in place (a removed triangle gets -1 in all three); wpart (nw) in 0..nparts-1, quota (nparts); params[P_COUNT];
 * stats[S_COUNT] out.
 * Returns the count, -1 on no memory. */
long ttt2_decimate(int npos, const double *pos, int nw, const int *wpos, int k, const double *attr, const int *sj,
                   const double *sw, const double *wnrm, const double *pfactor, const unsigned char *lock_in,
                   int ntri, int *tri, const int *wpart, int nparts, const long *quota, const double *params,
                   long target, double *stats)
{
    D d;
    long result = -1;
    memset(&d, 0, sizeof(d));
    if (k > MAXK)
        return -1;
    d.npos = npos; d.nw = nw; d.ntri = ntri; d.k = k; d.aq = 11 + 4 * k;
    d.pos = pos; d.attr = attr; d.sw = sw; d.wnrm = wnrm; d.pfactor = pfactor;
    d.wpos = wpos; d.sj = sj; d.wpart = wpart; d.quota = quota;
    d.tri = tri;
    d.feature_w = params[P_FEATURE]; d.flip_cos = params[P_FLIP]; d.corner_cos = params[P_CORNER];
    d.skin_w = params[P_SKIN]; d.reg = params[P_REG]; d.maxcost = params[P_MAXCOST];
    d.normal_cos = params[P_NORMAL];
    for (int i = 0; i < S_COUNT; i++)
        stats[i] = 0;
    d.q = calloc((size_t)npos * 10, sizeof(double));
    d.aqd = calloc((size_t)nw * d.aq, sizeof(double));
    d.warea = calloc(nw, sizeof(double));
    d.wref = calloc(nw, sizeof(int));
    d.lock = calloc(npos, 1);
    d.dead = calloc(npos, 1);
    d.tdead = calloc(ntri ? ntri : 1, 1);
    d.fcount = calloc(npos, sizeof(int));
    d.fnb = calloc((size_t)npos * 2, sizeof(int));
    d.ts = calloc(npos, sizeof(int));
    d.tn = calloc(npos, sizeof(int));
    d.tc = calloc(npos, sizeof(int));
    d.mark = calloc(npos, sizeof(int));
    d.version = calloc(npos, sizeof(int));
    d.target = calloc(npos, sizeof(int));
    d.plive = calloc(nparts, sizeof(long));
    d.pool_cap = (long)ntri * 6 + 1024;
    d.pool = malloc(d.pool_cap * sizeof(int));
    if (!d.q || !d.aqd || !d.warea || !d.wref || !d.lock || !d.dead || !d.tdead || !d.fcount || !d.fnb || !d.ts ||
        !d.tn || !d.tc || !d.mark || !d.version || !d.target || !d.plive || !d.pool)
        goto out;
    if (setup(&d, lock_in, stats))
        goto out;
    for (int v = 0; v < npos; v++)
        if (best(&d, v))
            goto out;
    while (d.live > target && d.hn > 0) {
        double c;
        int u, ver;
        pop(&d, &c, &u, &ver);
        if (d.dead[u] || ver != d.version[u] || d.target[u] < 0 || !above_quota(&d, u))
            continue;
        int v = d.target[u];
        if (d.dead[v] || !valid(&d, u, v)) {
            if (best(&d, u))
                goto out;
            continue;
        }
        int r = collapse(&d, u, v);
        if (r < 0)
            goto out;
        if (r == 0) {
            if (best(&d, u))
                goto out;
            continue;
        }
        stats[S_COLLAPSES] += 1;
        stats[S_LASTCOST] = c;
    }
    for (int t = 0; t < ntri; t++)
        if (d.tdead[t])
            tri[3 * t] = tri[3 * t + 1] = tri[3 * t + 2] = -1;
    result = d.live;
out:
    free(d.q); free(d.aqd); free(d.warea); free(d.wref); free(d.lock); free(d.dead); free(d.tdead); free(d.fcount);
    free(d.fnb); free(d.ts); free(d.tn); free(d.tc); free(d.mark); free(d.version); free(d.target); free(d.pool);
    free(d.hc); free(d.hv); free(d.hver); free(d.plive);
    return result;
}
