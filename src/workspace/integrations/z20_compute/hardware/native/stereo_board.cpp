#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/calib3d.hpp>
#include <cstring>

extern "C" int z_stereo_bm(int width,int height,int disparities,int block,
 const unsigned char *left,const unsigned char *right,const float *maps,float *output) {
 if(width!=160 || height!=180 || disparities!=32 || block!=15 || !left || !right || !maps || !output)return -1;
 try {
  const int size=width*height;
  cv::Mat l(height,width,CV_8UC1,const_cast<unsigned char*>(left));
  cv::Mat r(height,width,CV_8UC1,const_cast<unsigned char*>(right));
  cv::Mat m[4];for(int i=0;i<4;i++)m[i]=cv::Mat(height,width,CV_32FC1,const_cast<float*>(maps+i*size));
  cv::Mat a,b,raw,values;
  cv::remap(l,a,m[0],m[1],cv::INTER_LINEAR);cv::remap(r,b,m[2],m[3],cv::INTER_LINEAR);
  auto bm=cv::StereoBM::create(disparities,block);
  bm->setUniquenessRatio(15);bm->setTextureThreshold(10);bm->setSpeckleWindowSize(50);bm->setSpeckleRange(2);
  bm->compute(a,b,raw);raw.convertTo(values,CV_32FC1,1./16.);
  if(!values.isContinuous())return -2;
  std::memcpy(output,values.ptr<float>(),size*sizeof(float));return 0;
 }catch(...){return -3;}
}
