#include <cassert>
#include <cstdio>
#include <string>
#define INPUT 0x01 // Arduino core owns this macro; command enums must not collide.
#include "../esp32/MultiControlS3/CommandProtocol.h"
static bool parse(const char *s, NetworkRequest &r) { const char *err=nullptr; return parseNetworkRequest(s,strlen(s),r,err); }
int main() {
  NetworkRequest r; const char *error=nullptr;
  assert(parse(R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"input","input":"contact"})",r));
  assert(!parse(R"({"v":1,"source":"pc","seq":1,"device":"pendulum","action":"input","input":"contact"})",r));
  assert(!parse(R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"input","input":"other"})",r));
  const char *hello=R"({"v":1,"source":"pc","seq":4294967295,"device":"all","action":"hello"})";
  assert(parse(hello,r)); SourceSession session; assert(session.accepts(r,100,error)); session.consume(r,100,true);
  assert(parse(R"({"v":1,"source":"pc","seq":0,"device":"all","action":"heartbeat"})",r));
  assert(session.accepts(r,200,error)); session.consume(r,200,true);
  assert(!session.accepts(r,201,error));
  r.sequence=1; r.source=CommandSource::EYE; assert(!session.accepts(r,201,error));
  r.source=CommandSource::PC; assert(session.accepts(r,699,error)); session.consume(r,699,false);
  assert(session.lastFreshMs==200 && session.expired(701)); // Rejected commands cannot renew.
  assert(!session.accepts(r,701,error)); session.clear();
  assert(!session.accepts(r,702,error));
  const char *bad[]={
    R"({"v":1,"source":"pc","seq":1,"device":"all","action":"hello"}garbage)",
    R"({"v":1,"v":1,"source":"pc","seq":1,"device":"all","action":"hello"})",
    R"({"v":1,"source":"pc\u0000eye","seq":1,"device":"all","action":"hello"})",
    R"({"v":1,"source":"pc","seq":-1,"device":"all","action":"hello"})",
    R"({"v":1,"source":"pc","seq":4294967296,"device":"all","action":"hello"})",
    R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"pose","angles":[0,1,2,3,4,181]})",
    R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"pose","angles":[0,1,2,3,4,5.5]})",
    R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"pose","angles":[0,1,2,3,4,5,6]})",
    R"({"v":1,"source":"pc","seq":1,"device":"all","action":"enable"})",
    R"({"v":1,"source":"pc","seq":1,"device":"pendulum","action":"close"})",
    R"({"v":1,"source":"pc","seq":1,"device":"hand","action":"start"})",
    R"({"v":1,"source":"pc","seq":1,"device":"pendulum","action":"mode","mode":"glove"})",
    R"({"v":1,"source":"pc","seq":1,"device":"all","action":"hello","angles":null})",
    R"({"v":1,"source":"pc","seq":1,"device":"all","action":"hello","extra":0})"
  };
  for(auto s:bad) assert(!parse(s,r));
  std::string tooLong(1024,' '); assert(!parse(tooLong.c_str(),r));
  assert(parse(R"({"v":1,"source":"brain","seq":2,"device":"hand","action":"pose","angles":[0,1,2,3,4,180]})",r));
  assert(r.angles[5]==180 && r.source==CommandSource::BRAIN);
  SourceSession wrap; r.action=CommandAction::HELLO; wrap.consume(r,0xfffffff0,true);
  r.action=CommandAction::HEARTBEAT; ++r.sequence; assert(wrap.accepts(r,20,error));
  puts("Production network schema, bounded input, duplicate/NUL rejection, sequence and lease tests PASS");
}
