#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <cstring>

// JPEG SOF and encoded-length limits are checked by visual_wire before this call.
extern "C" int z_visual_decode(const unsigned char* encoded, int length, unsigned char* rgb) {
    if (!encoded || !rgb || length <= 0 || length > 1048576) return -1;
    try {
        cv::Mat input(1,length,CV_8UC1,const_cast<unsigned char*>(encoded));
        cv::Mat bgr=cv::imdecode(input,cv::IMREAD_COLOR);
        if (bgr.empty() || bgr.cols>1280 || bgr.rows>720) return -2;
        double scale=std::min(1280.0/bgr.cols,720.0/bgr.rows);
        int w=std::max(1,int(bgr.cols*scale)),h=std::max(1,int(bgr.rows*scale));
        // Convert at source resolution and resize directly into the output.
        // Channel permutation commutes with interpolation; avoid another full
        // RGB720p conversion, clearing and copy for the normal 16:9 profile.
        cv::Mat source_rgb;cv::cvtColor(bgr,source_rgb,cv::COLOR_BGR2RGB);
        cv::Mat output(720,1280,CV_8UC3,rgb);
        if (w!=1280 || h!=720) output.setTo(cv::Scalar(0,0,0));
        cv::Mat target=output(cv::Rect((1280-w)/2,(720-h)/2,w,h));
        cv::resize(source_rgb,target,cv::Size(w,h));return 0;
    } catch (...) { return -3; }
}
