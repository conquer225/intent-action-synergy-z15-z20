#include "command_wire.h"
#include <string.h>

static bool hex64(const char *data, uint64_t *value)
{
    *value = 0;
    for (size_t i = 0; i < 16; i++) {
        unsigned char c = (unsigned char)data[i];
        unsigned digit;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
        else return false;
        *value = (*value << 4) | digit;
    }
    return true;
}

bool wc_decode_command(const char *data, size_t size, wc_wire_command *command)
{
    static const char *const words[] = {"stop", "forward", "backward", "left", "right"};
    wc_wire_command parsed = {0, 0, WC_STOP};
    if (command == NULL) return false;
    *command = parsed;
    if (data == NULL || size < 38 || size > 42 || data[16] != ' ' || data[33] != ' ' ||
        !hex64(data, &parsed.boot_id) || !hex64(data + 17, &parsed.sequence)) return false;
    for (unsigned i = 0; i < sizeof(words) / sizeof(words[0]); i++) {
        if (strlen(words[i]) == size - 34 && memcmp(data + 34, words[i], size - 34) == 0) {
            parsed.direction = (wc_direction)i;
            if (parsed.direction != WC_STOP && (parsed.boot_id == 0 || parsed.sequence == 0)) return false;
            *command = parsed;
            return true;
        }
    }
    return false;
}

