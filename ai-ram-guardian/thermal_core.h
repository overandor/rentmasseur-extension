#ifndef THERMAL_CORE_H
#define THERMAL_CORE_H

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOReturn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/*
 * thermal_core.h — experimental read-only thermal sensor layer.
 *
 * Purpose:
 *   Native AI RAM Guardian thermal probe for local Mac builds.
 *   Reads temperature-like SMC keys when AppleSMC is exposed.
 *
 * Safety boundary:
 *   This header is read-only. It does not write SMC keys, set fan targets,
 *   override thermal policy, disable throttling, or bypass macOS protection.
 *   Fan fields below are RPM reads only, not control.
 *
 * Practical note:
 *   Apple Silicon machines vary. Some expose usable values through AppleSMC;
 *   some are better served by IOHID thermal sensors. The production app should
 *   treat this as an optional backend and fall back softly when unavailable.
 */

/* ------------------------------ SMC protocol ----------------------------- */

#define SMC_KEY_LEN 4
#define SMC_DATA_LEN 32

#define KERNEL_INDEX_SMC      2
#define SMC_CMD_READ_BYTES    5
#define SMC_CMD_READ_KEYINFO  9

typedef struct {
    uint32_t key;
    uint32_t dataSize;
    uint8_t  dataType[4];
    uint8_t  data[SMC_DATA_LEN];
} smc_val_t;

static io_connect_t g_smc_conn = 0;
static io_service_t g_smc_service = 0;

static bool smc_init(void) {
    if (g_smc_conn) return true;

    CFMutableDictionaryRef matching = IOServiceMatching("AppleSMC");
    if (!matching) return false;

    g_smc_service = IOServiceGetMatchingService(kIOMainPortDefault, matching);
    if (!g_smc_service) return false;

    kern_return_t kr = IOServiceOpen(g_smc_service, mach_task_self(), 0, &g_smc_conn);
    if (kr != kIOReturnSuccess) {
        IOObjectRelease(g_smc_service);
        g_smc_service = 0;
        g_smc_conn = 0;
        return false;
    }

    return true;
}

static void smc_close(void) {
    if (g_smc_conn) {
        IOServiceClose(g_smc_conn);
        g_smc_conn = 0;
    }
    if (g_smc_service) {
        IOObjectRelease(g_smc_service);
        g_smc_service = 0;
    }
}

#pragma pack(push, 1)
typedef struct {
    uint8_t  cmd;
    uint32_t pad;
    uint8_t  key[SMC_KEY_LEN];
} smc_key_in_t;

typedef struct {
    uint8_t  cmd;
    uint32_t pad;
    uint8_t  key[SMC_KEY_LEN];
    uint32_t dataSize;
    uint8_t  dataType[4];
    uint8_t  data[SMC_DATA_LEN];
} smc_key_out_t;
#pragma pack(pop)

static uint32_t smc_key_to_uint(const char *key) {
    return ((uint32_t)key[0] << 24) | ((uint32_t)key[1] << 16) |
           ((uint32_t)key[2] << 8)  |  (uint32_t)key[3];
}

static bool smc_read_key(const char *key, smc_key_out_t *out) {
    if (!key || !out) return false;
    if (!g_smc_conn && !smc_init()) return false;

    smc_key_in_t in = {0};
    in.cmd = SMC_CMD_READ_KEYINFO;
    memcpy(in.key, key, SMC_KEY_LEN);

    smc_key_out_t info = {0};
    size_t outSize = sizeof(info);
    kern_return_t kr = IOConnectCallStructMethod(
        g_smc_conn,
        KERNEL_INDEX_SMC,
        &in,
        sizeof(in),
        &info,
        &outSize
    );
    if (kr != kIOReturnSuccess) return false;

    smc_key_in_t read_in = {0};
    read_in.cmd = SMC_CMD_READ_BYTES;
    read_in.pad = info.dataSize;
    memcpy(read_in.key, key, SMC_KEY_LEN);

    memset(out, 0, sizeof(*out));
    outSize = sizeof(*out);
    kr = IOConnectCallStructMethod(
        g_smc_conn,
        KERNEL_INDEX_SMC,
        &read_in,
        sizeof(read_in),
        out,
        &outSize
    );

    out->dataSize = info.dataSize;
    memcpy(out->dataType, info.dataType, 4);
    return kr == kIOReturnSuccess;
}

/* --------------------------- value decoders ------------------------------ */

static double smc_flt_from_bytes(const uint8_t *data, uint32_t size) {
    if (!data || size < 4) return -1.0;

    uint32_t raw = ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16) |
                   ((uint32_t)data[2] << 8)  |  (uint32_t)data[3];
    float f = 0.0f;
    memcpy(&f, &raw, sizeof(f));
    return (double)f;
}

static double smc_sp78_to_double(const uint8_t *data, uint32_t size) {
    if (!data || size < 2) return -1.0;
    int16_t raw = (int16_t)(((uint16_t)data[0] << 8) | data[1]);
    return (double)raw / 256.0;
}

static double smc_sp5a_to_double(const uint8_t *data, uint32_t size) {
    if (!data || size < 2) return -1.0;
    int16_t raw = (int16_t)(((uint16_t)data[0] << 8) | data[1]);
    return (double)raw / 64.0;
}

static double smc_fpe2_to_double(const uint8_t *data, uint32_t size) {
    if (!data || size < 2) return -1.0;
    uint16_t raw = (uint16_t)(((uint16_t)data[0] << 8) | data[1]);
    return (double)raw / 4.0;
}

static double smc_decode_value(const smc_key_out_t *out) {
    if (!out || out->dataSize == 0) return -1.0;

    if (memcmp(out->dataType, "sp78", 4) == 0) return smc_sp78_to_double(out->data, out->dataSize);
    if (memcmp(out->dataType, "flt ", 4) == 0) return smc_flt_from_bytes(out->data, out->dataSize);
    if (memcmp(out->dataType, "sp5a", 4) == 0) return smc_sp5a_to_double(out->data, out->dataSize);
    if (memcmp(out->dataType, "fpe2", 4) == 0) return smc_fpe2_to_double(out->data, out->dataSize);

    return smc_sp78_to_double(out->data, out->dataSize);
}

/* -------------------------- temperature sensors -------------------------- */

typedef struct {
    double cpu_die;       /* Celsius: CPU die temperature when available. */
    double gpu_die;       /* Celsius: GPU die temperature when available. */
    double soc_die;       /* Celsius: SoC die temperature when available. */
    double palm_rest;     /* Celsius: palm-rest / enclosure sensor when available. */
    double battery_temp;  /* Celsius: battery sensor when available. */
    double ambient;       /* Celsius: ambient / inlet sensor when available. */
    bool   valid;
} thermal_reading_t;

static char g_cpu_key[5] = {0};
static char g_soc_key[5] = {0};
static char g_gpu_key[5] = {0};
static char g_amb_key[5] = {0};
static bool g_keys_discovered = false;

static const char *cpu_keys[] = {
    "Tp09", "Tp01", "Tp05", "Tp0D", "TC0c", "TC0D", "TC0P", "TC0E", "TC0F", "TC0G",
    "TC1c", "TC2c", "TC3c", "TC4c", "TC5c", "TC6c", "TC7c", "TC8c", "TC9c",
    "Tp02", "Tp03", "Tp04", "Tp06", "Tp07", "Tp08", "Tp0A", "Tp0B", "Tp0C",
    NULL
};

static const char *soc_keys[] = {
    "Ts0P", "Ts0S", "TW0P", "Tp0P", "Tp0T", "Ts1P", "TN0D", "TN0P", "TN1D",
    "Tp0E", "Tp0F", "Tp0G", "Tp0H", "Tp0J", "Tp0K", "Tp0L", "Tp0M", "Tp0N",
    NULL
};

static const char *gpu_keys[] = {
    "TG0P", "TG0T", "TG0c", "TG1c", "Tp0D", "TG0D", "TG0E", "TG0F",
    NULL
};

static const char *amb_keys[] = {
    "Ta0P", "Ta0V", "Ta1P", "Ta2P", "Ta3P", "Ta4P",
    NULL
};

static bool thermal_try_temp_key(const char *key, double *out_temp) {
    if (out_temp) *out_temp = -1.0;
    if (!key || !out_temp) return false;

    smc_key_out_t out;
    if (!smc_read_key(key, &out)) return false;

    double temp = smc_decode_value(&out);
    *out_temp = temp;
    return temp > 0.0 && temp < 150.0;
}

static void thermal_discover_keys(void) {
    if (g_keys_discovered) return;

    double t = -1.0;
    double best = -1.0;

    for (int i = 0; cpu_keys[i]; i++) {
        if (thermal_try_temp_key(cpu_keys[i], &t) && t > best) {
            best = t;
            memcpy(g_cpu_key, cpu_keys[i], 4);
            g_cpu_key[4] = '\0';
        }
    }

    best = -1.0;
    for (int i = 0; soc_keys[i]; i++) {
        if (thermal_try_temp_key(soc_keys[i], &t) && t > best) {
            best = t;
            memcpy(g_soc_key, soc_keys[i], 4);
            g_soc_key[4] = '\0';
        }
    }

    best = -1.0;
    for (int i = 0; gpu_keys[i]; i++) {
        if (thermal_try_temp_key(gpu_keys[i], &t) && t > best) {
            best = t;
            memcpy(g_gpu_key, gpu_keys[i], 4);
            g_gpu_key[4] = '\0';
        }
    }

    best = -1.0;
    for (int i = 0; amb_keys[i]; i++) {
        if (thermal_try_temp_key(amb_keys[i], &t) && t > best) {
            best = t;
            memcpy(g_amb_key, amb_keys[i], 4);
            g_amb_key[4] = '\0';
        }
    }

    g_keys_discovered = true;
    fprintf(stderr,
            "[thermal] keys: cpu=%s soc=%s gpu=%s amb=%s\n",
            g_cpu_key[0] ? g_cpu_key : "none",
            g_soc_key[0] ? g_soc_key : "none",
            g_gpu_key[0] ? g_gpu_key : "none",
            g_amb_key[0] ? g_amb_key : "none");
}

static double thermal_read_key(const char *key) {
    if (!key || !key[0]) return -1.0;

    smc_key_out_t out;
    if (!smc_read_key(key, &out)) return -1.0;
    return smc_decode_value(&out);
}

static thermal_reading_t thermal_read(void) {
    thermal_reading_t t;
    memset(&t, 0, sizeof(t));

    t.cpu_die = -1.0;
    t.gpu_die = -1.0;
    t.soc_die = -1.0;
    t.palm_rest = -1.0;
    t.battery_temp = -1.0;
    t.ambient = -1.0;

    if (!g_keys_discovered) thermal_discover_keys();

    t.cpu_die = thermal_read_key(g_cpu_key);
    t.gpu_die = thermal_read_key(g_gpu_key);
    t.soc_die = thermal_read_key(g_soc_key);
    t.ambient = thermal_read_key(g_amb_key);

    t.battery_temp = thermal_read_key("TB0T");
    if (t.battery_temp < 0) t.battery_temp = thermal_read_key("TB1T");
    if (t.battery_temp < 0) t.battery_temp = thermal_read_key("TB2T");

    t.palm_rest = thermal_read_key("Ts1P");
    if (t.palm_rest < 0) t.palm_rest = thermal_read_key("Ts2P");

    t.valid = (t.cpu_die > 0.0 || t.soc_die > 0.0 || t.gpu_die > 0.0);
    return t;
}

/* ------------------------------ fan reads -------------------------------- */

typedef struct {
    double actual_rpm;
    double target_rpm;
    double max_rpm;
    bool   valid;
} fan_reading_t;

static double smc_read_numeric_key(const char *key) {
    smc_key_out_t out;
    if (!smc_read_key(key, &out)) return -1.0;
    return smc_decode_value(&out);
}

static fan_reading_t fan_read(int fan_id) {
    fan_reading_t f;
    memset(&f, 0, sizeof(f));

    f.actual_rpm = -1.0;
    f.target_rpm = -1.0;
    f.max_rpm = -1.0;

    char key[5];

    snprintf(key, sizeof(key), "F%dAc", fan_id);
    f.actual_rpm = smc_read_numeric_key(key);

    snprintf(key, sizeof(key), "F%dTg", fan_id);
    f.target_rpm = smc_read_numeric_key(key);

    snprintf(key, sizeof(key), "F%dMx", fan_id);
    f.max_rpm = smc_read_numeric_key(key);

    f.valid = (f.actual_rpm > 0.0);
    return f;
}

/* ------------------------- thermal history buffer ------------------------- */

#define THERMAL_HISTORY_LEN 256

typedef struct {
    thermal_reading_t readings[THERMAL_HISTORY_LEN];
    double timestamps[THERMAL_HISTORY_LEN];
    int head;
    int count;
} thermal_history_t;

static thermal_history_t g_thermal_hist = {0};

static void thermal_history_push(thermal_reading_t r, double ts) {
    g_thermal_hist.readings[g_thermal_hist.head] = r;
    g_thermal_hist.timestamps[g_thermal_hist.head] = ts;
    g_thermal_hist.head = (g_thermal_hist.head + 1) % THERMAL_HISTORY_LEN;
    if (g_thermal_hist.count < THERMAL_HISTORY_LEN) g_thermal_hist.count++;
}

static thermal_reading_t thermal_history_get(int idx) {
    if (idx < 0 || idx >= g_thermal_hist.count) {
        thermal_reading_t empty;
        memset(&empty, 0, sizeof(empty));
        empty.cpu_die = -1.0;
        empty.gpu_die = -1.0;
        empty.soc_die = -1.0;
        empty.palm_rest = -1.0;
        empty.battery_temp = -1.0;
        empty.ambient = -1.0;
        empty.valid = false;
        return empty;
    }

    int pos = (g_thermal_hist.head - 1 - idx + THERMAL_HISTORY_LEN) % THERMAL_HISTORY_LEN;
    return g_thermal_hist.readings[pos];
}

#endif /* THERMAL_CORE_H */
