#pragma once
#include <map>
#include <string>
#include <vector>
#include <cstring>
inline std::map<std::string,std::vector<uint8_t>> fakeNvs;
class Preferences {
 public:
  bool begin(const char*, bool) { return true; }
  size_t getBytesLength(const char *key) { return fakeNvs[key].size(); }
  size_t getBytes(const char *key, void *out, size_t count) {
    if (fakeNvs[key].size() != count) return 0;
    memcpy(out, fakeNvs[key].data(), count); return count;
  }
  size_t putBytes(const char *key, const void *data, size_t count) {
    const uint8_t *p = (const uint8_t*)data;
    fakeNvs[key] = std::vector<uint8_t>(p, p+count); return count;
  }
};
