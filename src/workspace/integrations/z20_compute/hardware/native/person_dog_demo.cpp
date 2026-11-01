// Native adapter to the vendor OpenCV 3.4 libraries; no Python cv2 extension.
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/videoio.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/calib3d.hpp>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

struct Photos {
    cv::Ptr<cv::ORB> orb=cv::ORB::create(2000);
    std::vector<cv::KeyPoint> points[3];
    cv::Mat descriptors[3];
};
struct Video {cv::VideoCapture capture; int frame=0; double fps=0;};

extern "C" {
void *z_photos_open(const char *a,const char *b,const char *c) {
    try {
        Photos *p=new Photos; const char *paths[]={a,b,c};
        for(int i=0;i<3;i++){
            cv::Mat image=cv::imread(paths[i],cv::IMREAD_GRAYSCALE);
            if(image.size()!=cv::Size(640,480)){delete p;return nullptr;}
            p->orb->detectAndCompute(image,cv::noArray(),p->points[i],p->descriptors[i]);
        }
        return p;
    }catch(...){return nullptr;}
}
void z_photos_close(void *pointer){delete static_cast<Photos*>(pointer);}

// Returns scene ID or -1. H maps registered image pixels to current camera pixels.
int z_photos_match(void *pointer,const unsigned char *rgb,int w,int h,
                   double *matrix,int *inliers) {
    if(!pointer||!rgb||w<80||h<80||!matrix||!inliers)return -2;
    *inliers=0; std::fill(matrix,matrix+9,0.);
    try {
        Photos *p=static_cast<Photos*>(pointer);cv::Mat gray;
        cv::cvtColor(cv::Mat(h,w,CV_8UC3,const_cast<unsigned char*>(rgb)),gray,cv::COLOR_RGB2GRAY);
        std::vector<cv::KeyPoint> points;cv::Mat descriptors;
        p->orb->detectAndCompute(gray,cv::noArray(),points,descriptors);
        if(descriptors.empty())return -1;
        int best=-1;cv::BFMatcher matcher(cv::NORM_HAMMING);
        for(int i=0;i<3;i++){
            std::vector<std::vector<cv::DMatch>> pairs;
            matcher.knnMatch(p->descriptors[i],descriptors,pairs,2);
            std::vector<cv::Point2f> a,b;
            for(auto &pair:pairs)if(pair.size()==2&&pair[0].distance<.72*pair[1].distance){
                a.push_back(p->points[i][pair[0].queryIdx].pt);
                b.push_back(points[pair[0].trainIdx].pt);
            }
            if(a.size()<15)continue;
            cv::Mat mask,H=cv::findHomography(a,b,cv::RANSAC,3.,mask);
            if(H.empty())continue;
            int count=cv::countNonZero(mask);
            if(count<15||count<double(a.size())*.45||count<=*inliers)continue;
            std::vector<cv::Point2f> corners={{0,0},{639,0},{639,479},{0,479}},quad;
            cv::perspectiveTransform(corners,quad,H);
            double area=std::abs(cv::contourArea(quad));
            bool finite=true;for(auto q:quad)finite&=std::isfinite(q.x)&&std::isfinite(q.y);
            if(!finite||!cv::isContourConvex(quad)||area<.04*w*h||area>1.5*w*h)continue;
            best=i;*inliers=count;
            for(int k=0;k<9;k++)matrix[k]=H.at<double>(k/3,k%3);
        }
        return best;
    }catch(...){return -2;}
}

void *z_video_open(const char *path){
    try {Video *v=new Video;
        v->capture.open(path,std::strstr(path,".avi")?cv::CAP_OPENCV_MJPEG:cv::CAP_ANY);
        v->fps=v->capture.get(cv::CAP_PROP_FPS);
        if(!v->capture.isOpened()||v->fps<=0){delete v;return nullptr;}return v;
    }catch(...){return nullptr;}
}
int z_video_next(void *pointer,unsigned char *rgb,double *time_s){
    if(!pointer||!rgb||!time_s)return -1;
    try {Video *v=static_cast<Video*>(pointer);cv::Mat source,small;
        if(!v->capture.read(source))return 0;
        cv::resize(source,small,cv::Size(640,360),0,0,cv::INTER_AREA);
        cv::Mat target(480,640,CV_8UC3,rgb);target.setTo(cv::Scalar(255,255,255));
        cv::cvtColor(small,target(cv::Rect(0,60,640,360)),cv::COLOR_BGR2RGB);
        *time_s=(v->frame++)/v->fps;return 1;
    }catch(...){return -1;}
}
void z_video_close(void *pointer){delete static_cast<Video*>(pointer);}

// Background and output are RGB888 1280x720. Input aspect ratio is preserved.
int z_render(const unsigned char *input,int w,int h,const unsigned char *background,
             const double *boxes,const double *geometry,int valid,unsigned char *output){
    if(!input||!background||!output||w<=0||h<=0)return -1;
    try{
        std::memcpy(output,background,1280*720*3);
        cv::Mat dst(720,1280,CV_8UC3,output),image(h,w,CV_8UC3,const_cast<unsigned char*>(input));
        dst(cv::Rect(40,100,720,540)).setTo(cv::Scalar(250,248,243));
        double scale=std::min(720./w,540./h);
        int tw=std::lround(w*scale),th=std::lround(h*scale),x=40+(720-tw)/2,y=100+(540-th)/2;
        cv::resize(image,dst(cv::Rect(x,y,tw,th)),cv::Size(tw,th),0,0,cv::INTER_AREA);
        if(!valid)return 0;
        cv::Point centers[2];
        for(int i=0;i<2;i++){
            cv::Point a(x+std::lround(boxes[4*i]*scale),y+std::lround(boxes[4*i+1]*scale));
            cv::Point b(x+std::lround(boxes[4*i+2]*scale),y+std::lround(boxes[4*i+3]*scale));
            cv::rectangle(dst,a,b,i==0?cv::Scalar(211,51,44):cv::Scalar(41,151,77),3);
            centers[i]=(a+b)*.5;
        }
        cv::line(dst,centers[0],centers[1],cv::Scalar(255,255,255),7);
        cv::line(dst,centers[0],centers[1],cv::Scalar(38,36,33),2);
        char text[96];
        dst(cv::Rect(805,365,420,65)).setTo(cv::Scalar(250,248,243));
        std::snprintf(text,sizeof text,"%.2f m",geometry[2]);
        cv::putText(dst,text,cv::Point(810,410),cv::FONT_HERSHEY_SIMPLEX,1.4,cv::Scalar(38,36,33),2,cv::LINE_AA);
        for(int i=0;i<2;i++){
            dst(cv::Rect(920,446+i*42,310,38)).setTo(cv::Scalar(250,248,243));
            std::snprintf(text,sizeof text,"%.2f m",geometry[i]);
            cv::putText(dst,text,cv::Point(930,477+i*42),cv::FONT_HERSHEY_SIMPLEX,.8,cv::Scalar(38,36,33),2,cv::LINE_AA);
        }
        return 0;
    }catch(...){return -1;}
}
}
