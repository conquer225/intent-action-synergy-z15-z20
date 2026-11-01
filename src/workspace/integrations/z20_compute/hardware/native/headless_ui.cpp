#include <stdint.h>

// Blend a whole text run in one call. Pixel arithmetic matches the NumPy path.
extern "C" int z_ui_text(uint8_t *frame,int width,int height,const uint8_t *masks,
    const int16_t *advances,int glyph_count,int cell,const uint32_t *indices,int count,
    int x,int y,int max_width,int red,int green,int blue) {
    if(!frame||!masks||!advances||!indices||width!=1280||height!=720||
       glyph_count<1||cell<1||cell>128||count<0||count>512)return -1;
    int cursor=x;const int color[3]={red,green,blue};int drawn=0;
    for(int i=0;i<count;++i){
        unsigned index=indices[i];if(index>=unsigned(glyph_count))return -1;
        int advance=advances[index];if(advance<1||cursor+advance>x+max_width)break;
        if(cursor>=0&&y>=0){
            const uint8_t *glyph=masks+index*cell*cell;
            for(int row=0;row<cell&&y+row<height;++row){
                for(int col=0;col<cell&&cursor+col<width;++col){
                    unsigned alpha=glyph[row*cell+col];if(!alpha)continue;
                    uint8_t *pixel=frame+((y+row)*width+cursor+col)*3;
                    for(int c=0;c<3;++c)pixel[c]=uint8_t((unsigned(pixel[c])*(255-alpha)+unsigned(color[c])*alpha+127)/255);
                }
            }
        }
        cursor+=advance;++drawn;
    }
    return drawn;
}
