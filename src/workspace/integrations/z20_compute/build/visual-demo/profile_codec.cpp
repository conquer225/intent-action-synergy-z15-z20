#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <cstring>
#include <time.h>
#include <cstdio>
static double now(){timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}

// JPEG SOF and encoded-length limits are checked by visual_wire before this call.
extern "C" int z_visual_decode(const unsigned char* encoded, int length, unsigned char* rgb) {
    if (!encoded || !rgb || length <= 0 || length > 1048576) return -1;
    try {
        double t0=now();
        cv::Mat input(1,length,CV_8UC1,const_cast<unsigned char*>(encoded));
        cv::Mat bgr=cv::imdecode(input,cv::IMREAD_COLOR);
        if (bgr.empty() || bgr.cols>1280 || bgr.rows>720) return -2;
        double t1=now();
        double scale=std::min(1280.0/bgr.cols,720.0/bgr.rows);
        int w=std::max(1,int(bgr.cols*scale)),h=std::max(1,int(bgr.rows*scale));
        cv::Mat resized;cv::resize(bgr,resized,cv::Size(w,h));double t2=now();cv::cvtColor(resized,resized,cv::COLOR_BGR2RGB);
        double t3=now();
        cv::Mat output(720,1280,CV_8UC3,rgb);output.setTo(cv::Scalar(0,0,0));
        resized.copyTo(output(cv::Rect((1280-w)/2,(720-h)/2,w,h)));fprintf(stderr,"CODEC_STAGE %.6f %.6f %.6f %.6f\n",t1-t0,t2-t1,t3-t2,now()-t3);return 0;
    } catch (...) { return -3; }
}
