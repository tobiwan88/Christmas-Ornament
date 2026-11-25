/* A* on a 2-layer grid with 8 directions, one 45-degree turn per step, turn and via penalties.
   Used by gen/tree_b_route.py through ctypes (compiled on demand: cc -O2 -shared).
   State = (layer, i, j, d), d = arrival direction 0..7 (E, SE, S, SW, W, NW, N, NE).  Sources start with all 8 directions. */
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef struct { float f; float g; int s; } Node;

static Node *heap; static long hn, hcap;
static void hpush(Node n) {
    if (hn == hcap) { hcap *= 2; heap = realloc(heap, hcap * sizeof(Node)); }
    long i = hn++;
    while (i > 0) { long p = (i - 1) / 2; if (heap[p].f <= n.f) break; heap[i] = heap[p]; i = p; }
    heap[i] = n;
}
static Node hpop(void) {
    Node top = heap[0], last = heap[--hn];
    long i = 0;
    for (;;) {
        long c = 2 * i + 1; if (c >= hn) break;
        if (c + 1 < hn && heap[c + 1].f < heap[c].f) c++;
        if (heap[c].f >= last.f) break;
        heap[i] = heap[c]; i = c;
    }
    if (hn) heap[i] = last;
    return top;
}

static const int DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};

/* returns the number of path states (l,i,j,d written as 4 ints each, source first), -1 = not found, -2 = node cap */
int astar(int ny, int nx, const unsigned char *blk_t, const unsigned char *blk_v, const unsigned char *src,
          const unsigned char *tgt, const int *tpi, const int *tpj, int ntp, float turn_cost, float via_cost,
          float hw, float step, int bi0, int bi1, int bj0, int bj1, long max_nodes, int *out, int max_out) {
    long plane = (long)ny * nx;
    long nstates = 2 * plane * 8;
    float *gc = malloc(nstates * sizeof(float));
    int *par = malloc(nstates * sizeof(int));
    if (!gc || !par) return -3;
    for (long k = 0; k < nstates; k++) { gc[k] = 1e30f; par[k] = -1; }
    hcap = 1 << 20; hn = 0; heap = malloc(hcap * sizeof(Node));
    const float DIAG = 1.41421356f;
#define H(i, j) ({ float b_ = 1e30f; for (int q_ = 0; q_ < ntp; q_++) { float dx_ = fabsf((float)((j) - tpj[q_])), dy_ = fabsf((float)((i) - tpi[q_])); \
        float mn_ = dx_ < dy_ ? dx_ : dy_, mx_ = dx_ < dy_ ? dy_ : dx_; float v_ = (mx_ - mn_) + DIAG * mn_; if (v_ < b_) b_ = v_; } b_ * step; })
    for (int l = 0; l < 2; l++)
        for (int i = bi0; i <= bi1; i++)
            for (int j = bj0; j <= bj1; j++)
                if (src[l * plane + (long)i * nx + j])
                    for (int d = 0; d < 8; d++) {
                        long s = (l * plane + (long)i * nx + j) * 8 + d;
                        gc[s] = 0; Node n = {hw * H(i, j), 0, (int)s}; hpush(n);
                    }
    long expanded = 0; int goal = -1; int rc = -1;
    while (hn) {
        Node cur = hpop();
        if (cur.g > gc[cur.s]) continue;
        long cell = cur.s / 8; int d = cur.s % 8;
        int l = cell / plane; long rem = cell % plane; int i = rem / nx, j = rem % nx;
        if (tgt[cell]) { goal = cur.s; break; }
        if (++expanded > max_nodes) { rc = -2; break; }
        for (int k = -1; k <= 1; k++) {
            int nd = (d + k + 8) % 8;
            int ni = i + DY[nd], nj = j + DX[nd];
            if (ni < bi0 || ni > bi1 || nj < bj0 || nj > bj1) continue;
            long lo = (long)l * plane;
            if (blk_t[lo + (long)ni * nx + nj]) continue;
            if (DX[nd] && DY[nd] && (blk_t[lo + (long)i * nx + nj] || blk_t[lo + (long)ni * nx + j])) continue;
            float c = ((DX[nd] && DY[nd]) ? DIAG * step : step) + (k ? turn_cost : 0);
            long ns = (lo + (long)ni * nx + nj) * 8 + nd;
            float ng = cur.g + c;
            if (ng < gc[ns]) { gc[ns] = ng; par[ns] = cur.s; Node n = {ng + hw * H(ni, nj), ng, (int)ns}; hpush(n); }
        }
        if (!blk_v[(long)i * nx + j] && !blk_t[(long)(1 - l) * plane + (long)i * nx + j]) {
            long ns = ((long)(1 - l) * plane + (long)i * nx + j) * 8 + d;
            float ng = cur.g + via_cost;
            if (ng < gc[ns]) { gc[ns] = ng; par[ns] = cur.s; Node n = {ng + hw * H(i, j), ng, (int)ns}; hpush(n); }
        }
    }
    int n = rc;
    if (goal >= 0) {
        int cnt = 0; long s = goal;
        while (s >= 0 && cnt < max_out) { long cell = s / 8; int d = s % 8; int l = cell / plane; long rem = cell % plane;
            out[cnt * 4] = l; out[cnt * 4 + 1] = rem / nx; out[cnt * 4 + 2] = rem % nx; out[cnt * 4 + 3] = d; cnt++; s = par[s]; }
        n = cnt;
    }
    free(gc); free(par); free(heap);
    return n;
}
