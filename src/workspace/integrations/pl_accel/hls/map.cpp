#include <stdint.h>

namespace {
int64_t magnitude(int64_t v) {return v<0 ? -v : v;}
int64_t r16(int64_t v) {int64_t q=(magnitude(v)+32768)>>16;return v<0 ? -q : q;}
int64_t divide(int64_t numerator,int64_t denominator) {
#pragma HLS INLINE off
    uint64_t a=(uint64_t)magnitude(numerator),b=(uint64_t)magnitude(denominator),q=0,remainder=0;
    for(int bit=63;bit>=0;--bit) {
#pragma HLS PIPELINE off
        remainder=(remainder<<1)|((a>>bit)&1);
        if(remainder>=b){remainder-=b;q|=uint64_t(1)<<bit;}
    }
    return (numerator<0)!=(denominator<0) ? -(int64_t)q : (int64_t)q;
}
struct Point {int x,y,z;bool valid;};
Point project(const int32_t *v,const int32_t *p) {
#pragma HLS INLINE
    int64_t xyz[3];
    for(unsigned r=0;r<3;++r) {
        int64_t value=(int64_t)p[12+r*4+3]*65536;
        for(unsigned c=0;c<3;++c)value+=(int64_t)p[12+r*4+c]*v[c];
        xyz[r]=r16(value);
    }
    Point out={0,0,0,false};
    if(xyz[2]<p[6] || xyz[2]>p[7])return out;
    for(unsigned c=0;c<3;++c)if(magnitude(xyz[c])>=2147483648LL)return out;
    int64_t u=r16(divide((int64_t)p[24]*xyz[0],xyz[2])+p[26]);
    int64_t w=r16(divide((int64_t)p[25]*xyz[1],xyz[2])+p[27]);
    if(magnitude(u)>1048576 || magnitude(w)>1048576)return out;
    out.x=(int)u;out.y=(int)w;out.z=(int)xyz[2];out.valid=true;return out;
}
unsigned code(int x,int y,unsigned width,unsigned height) {
    return (x<0 ? 1 : x>=(int)width ? 2 : 0)|(y<0 ? 4 : y>=(int)height ? 8 : 0);
}
bool clip(Point &a,Point &b,unsigned width,unsigned height) {
#pragma HLS INLINE
    for(unsigned i=0;i<8;++i) {
        unsigned c0=code(a.x,a.y,width,height),c1=code(b.x,b.y,width,height);
        if(!(c0|c1))return true;
        if(c0&c1)return false;
        unsigned c=c0 ? c0 : c1;int x,y;
        if(c&8) {y=height-1;x=a.x+(int)divide((int64_t)(b.x-a.x)*(y-a.y),b.y-a.y);}
        else if(c&4) {y=0;x=a.x+(int)divide((int64_t)(b.x-a.x)*(-a.y),b.y-a.y);}
        else if(c&2) {x=width-1;y=a.y+(int)divide((int64_t)(b.y-a.y)*(x-a.x),b.x-a.x);}
        else {x=0;y=a.y+(int)divide((int64_t)(b.y-a.y)*(-a.x),b.x-a.x);}
        if(c==c0) {a.x=x;a.y=y;}else {b.x=x;b.y=y;}
    }
    return false;
}
}

extern "C" void z20_map(const int32_t *vertices,const int32_t *parameters,
                         int32_t *frame,int32_t *depth,int32_t *stats) {
#pragma HLS INTERFACE m_axi port=vertices offset=slave bundle=geometry depth=266240
#pragma HLS INTERFACE m_axi port=parameters offset=slave bundle=geometry depth=32
#pragma HLS INTERFACE m_axi port=frame offset=slave bundle=pixels depth=921600
#pragma HLS INTERFACE m_axi port=depth offset=slave bundle=zbuffer depth=921600
#pragma HLS INTERFACE m_axi port=stats offset=slave bundle=geometry depth=16
#pragma HLS INTERFACE s_axilite port=vertices bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=parameters bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=frame bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=depth bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=stats bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ALLOCATION operation instances=mul limit=8
#pragma HLS ALLOCATION instances=divide limit=1 function
    int32_t p[32];
    for(unsigned i=0;i<32;++i)p[i]=parameters[i];
    for(unsigned i=0;i<16;++i)stats[i]=0;
    stats[0]=0x4d415031;
    unsigned width=p[2],height=p[3],points=p[4],trajectory=p[5],radius=p[8];
    if(p[0]!=0x4d415031 || p[1]!=1 || width<1 || width>1280 || height<1 || height>720
       || points>65536 || trajectory>1024 || radius>2 || p[6]<1 || p[7]<=p[6]
       || p[7]>134217728 || p[24]<1 || p[24]>268435456 || p[25]<1 || p[25]>268435456) {
        stats[1]=1;return;
    }
    for(unsigned i=12;i<24;++i)if(magnitude(p[i])>134217728){stats[1]=1;return;}
    for(unsigned i=0;i<width*height;++i) {
#pragma HLS PIPELINE II=1
        frame[i]=p[9]&0xffffff;depth[i]=2147483647;
    }
    unsigned visible=0,clipped=0,segments=0,pixels=0;
    for(unsigned i=0;i<points;++i) {
        int32_t vertex[4];for(unsigned c=0;c<4;++c)vertex[c]=vertices[i*4+c];
        Point q=project(vertex,p);
        if(!q.valid || code(q.x,q.y,width,height)) {++clipped;continue;}
        ++visible;
        for(int dy=-2;dy<=2;++dy)for(int dx=-2;dx<=2;++dx) {
            int x=q.x+dx,y=q.y+dy;
            if(magnitude(dx)>radius || magnitude(dy)>radius || code(x,y,width,height))continue;
            unsigned address=y*width+x;
            if(q.z<depth[address]){depth[address]=q.z;frame[address]=vertex[3]&0xffffff;}
        }
    }
    Point previous={0,0,0,false};
    for(unsigned i=0;i<trajectory;++i) {
        int32_t vertex[4];for(unsigned c=0;c<4;++c)vertex[c]=vertices[(points+i)*4+c];
        Point current=project(vertex,p);
        if(previous.valid && current.valid) {
            Point a=previous,b=current;
            if(clip(a,b,width,height)) {
                int dx=(int)magnitude(b.x-a.x),dy=-(int)magnitude(b.y-a.y);
                int sx=a.x<b.x ? 1 : -1,sy=a.y<b.y ? 1 : -1,error=dx+dy;
                for(unsigned step=0;step<2001;++step) {
                    frame[a.y*width+a.x]=p[10]&0xffffff;++pixels;
                    if(a.x==b.x && a.y==b.y)break;
                    int twice=error*2;
                    if(twice>=dy){error+=dy;a.x+=sx;}
                    if(twice<=dx){error+=dx;a.y+=sy;}
                }
                ++segments;
            }
        }
        previous=current;
    }
    stats[2]=visible;stats[3]=clipped;stats[4]=segments;stats[5]=pixels;stats[6]=p[11];
}
