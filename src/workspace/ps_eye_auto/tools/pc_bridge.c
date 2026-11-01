/* Windows host ABI checks; production inference sources stay unchanged. */
#include <stddef.h>
#include "auto_face.h"
unsigned pc_abi_value(unsigned index)
{
    static const unsigned layout[]={sizeof(EyeRoi),sizeof(EyeFaceBox),sizeof(Localization),
        offsetof(Localization,face),offsetof(Localization,left),offsetof(Localization,right),
        offsetof(Localization,valid),offsetof(Localization,faces),offsetof(Localization,eye_count)};
    return index<sizeof(layout)/sizeof(layout[0])?layout[index]:0;
}
