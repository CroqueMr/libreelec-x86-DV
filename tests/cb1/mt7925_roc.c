/* Compile with the replayed MT7925 callbacks inserted at DRIVER. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

typedef unsigned char u8;
typedef unsigned short u16;
struct work_struct { int dummy; };
struct ieee80211_channel { int dummy; };
struct ieee80211_hw { int dummy; };
struct mt76_phy { unsigned long state; struct ieee80211_hw *hw; };
struct mt792x_phy {
    struct mt76_phy *mt76;
    struct mt792x_dev *dev;
    struct work_struct roc_work;
    bool roc_timer, roc_grant;
    u8 roc_token_id;
    struct mt792x_bss_conf *roc_join_owner;
};
struct mt792x_dev { struct mt792x_phy phy; struct { struct ieee80211_hw *hw; } mt76; };
struct mt76_dev { int dummy; };
struct mt792x_bss_conf {
    struct { struct context { struct { struct ieee80211_channel *chan; } def; } *ctx; } mt76;
};
struct mt792x_vif { struct mt792x_bss_conf bss_conf; struct mt792x_phy *phy; bool roc_join_held; };
struct ieee80211_vif { struct mt792x_vif *drv_priv; int type; bool mld; };
struct ieee80211_sta { struct ieee80211_link_sta { int id; } deflink; bool tdls; void *drv_priv; };
struct mt792x_sta { int deflink_id; };
struct ieee80211_prep_tx_info { int subtype, duration; bool success; };
enum mt76_sta_event { MT76_STA_EVENT_ASSOC, MT76_STA_EVENT_AUTHORIZE, MT76_STA_EVENT_DISASSOC };
enum mt7925_roc_req { MT7925_ROC_REQ_JOIN, MT7925_ROC_REQ_ROC };
enum ieee80211_roc_type { OFFCHANNEL };
enum { IEEE80211_STYPE_ASSOC_REQ, IEEE80211_STYPE_REASSOC_REQ, NL80211_IFTYPE_STATION };

static struct mt792x_dev device;
static struct mt76_phy radio;
static struct context ctx;
static struct mt792x_vif ifdata[2];
static struct ieee80211_vif vif[2];
static bool locked, fail_grant, woke_without_timer, worker_running;
static int aborted, expired;
#define MT76_STATE_ROC 0
#define HZ 1000
#define jiffies_to_msecs(x) (x)
#define mt792x_hw_dev(...) (&device)
#define mt792x_hw_phy(...) (&device.phy)
#define mt76_hw(...) (radio.hw)
#define ieee80211_vif_is_mld(v) ((v)->mld)
#define mt792x_sta_to_link_sta(v,s,id) (&(s)->deflink)
#define mt7925_mac_set_links(...) ((void)0)
#define mt7925_mac_link_sta_assoc(...) ((void)0)
#define WARN_ON_ONCE(x) (x)
#define EXPORT_SYMBOL_GPL(x)
#define container_of(ptr,type,member) ((type *)((char *)(ptr) - offsetof(type,member)))
#define timer_delete_sync(timer) (*(timer) = false)
#define timer_pending(timer) (*(timer))
#define cancel_work(work) ((void)0)
#define cancel_work_sync(work) do { assert(!locked); worker_running = false; } while (0)
#define mt792x_mutex_acquire(d) do { assert(!locked); locked = true; } while (0)
#define mt792x_mutex_release(d) do { assert(locked); locked = false; } while (0)
#define wait_event_timeout(q,cond,t) (cond)
#define test_and_clear_bit(bit,p) __atomic_exchange_n(p, 0, __ATOMIC_SEQ_CST)
#define test_and_set_bit(bit,p) __atomic_exchange_n(p, 1, __ATOMIC_SEQ_CST)
#define clear_bit(bit,p) (*(p) = 0)
#define ieee80211_remain_on_channel_expired(hw) (++expired)
#define ieee80211_iterate_interfaces(hw,flags,cb,data) cb(data, NULL, &vif[0])
#define ieee80211_iterate_active_interfaces ieee80211_iterate_interfaces

struct tlv { u16 tag; };
struct mt7925_roc_grant_tlv { u16 tag, reqtype; int max_interval; };
#define UNI_EVENT_ROC_GRANT 1
#define le16_to_cpu(val) (val)
#define le32_to_cpu(val) (val)
#define jiffies 0
#define msecs_to_jiffies(val) (val)
#define mod_timer(timer, deadline) (*(timer) = true)
#define smp_store_release(p,v) (*(p) = (v))
#define smp_load_acquire(p) (*(p))
#define ieee80211_ready_on_channel(hw) ((void)0)
#define ieee80211_iterate_active_interfaces_atomic(...) ((void)0)
#define wake_up(q) (woke_without_timer = !device.phy.roc_timer)

/* GRANT */

static int mt7925_mcu_set_roc(struct mt792x_phy *p, struct mt792x_bss_conf *b,
                              struct ieee80211_channel *ch, int ms, int type, u8 token) {
    assert(locked);
    if (fail_grant)
        return -EIO;
    struct mt7925_roc_grant_tlv grant = { UNI_EVENT_ROC_GRANT, type, ms };
    mt7925_mcu_roc_handle_grant(p->dev, (struct tlv *)&grant);
    return 0;
}
#define mt7925_mcu_set_mlo_roc(p,b,links,d,t) mt7925_mcu_set_roc(p,b,NULL,d,0,t)
static int mt7925_mcu_abort_roc(struct mt792x_phy *p, struct mt792x_bss_conf *b, u8 t) {
    assert(locked && t == p->roc_token_id);
    ++aborted;
    return 0;
}

/* DRIVER */

int main(int argc, char **argv) {
    assert(argc == 2);
    const char *s = argv[1];
    bool busy = !strcmp(s, "busy") || !strcmp(s, "busy-reject");
    struct ieee80211_prep_tx_info assoc = {
        .subtype = !strcmp(s, "reassoc") ? IEEE80211_STYPE_REASSOC_REQ : IEEE80211_STYPE_ASSOC_REQ,
        .success = strcmp(s, "rejected") && strcmp(s, "busy-reject"),
    };
    struct ieee80211_sta sta = {0};
    device.phy.dev = &device;
    device.phy.mt76 = &radio;
    for (int i = 0; i < 2; ++i) {
        ifdata[i].phy = &device.phy;
        ifdata[i].bss_conf.mt76.ctx = &ctx;
        vif[i].drv_priv = &ifdata[i];
        vif[i].type = NL80211_IFTYPE_STATION;
    }
    vif[0].mld = !strcmp(s, "mlo");
    fail_grant = !strcmp(s, "failed");
    if (busy)
        assert(!mt7925_remain_on_channel(NULL, &vif[1], NULL, 50, OFFCHANNEL));
    mt7925_mgd_prepare_tx(NULL, &vif[0], &assoc);
    if (!strcmp(s, "grant")) {
        assert(!woke_without_timer);
        return 0;
    }
    if (!strcmp(s, "open"))
        mt7925_mac_sta_event(NULL, &vif[0], &sta, MT76_STA_EVENT_AUTHORIZE);
    if (vif[0].mld) {
        /* Link activation replaces the management ROC before completion. */
        mt7925_abort_roc(&device.phy, &ifdata[0].bss_conf);
        mt792x_mutex_acquire(&device);
        assert(!mt7925_set_mlo_roc(&device.phy, &ifdata[0].bss_conf, 3));
        mt792x_mutex_release(&device);
    }
    mt7925_mgd_complete_tx(NULL, &vif[0], &assoc);

    if (!strcmp(s, "open") || !strcmp(s, "mlo") || !strcmp(s, "rejected")) {
        assert(!radio.state && !device.phy.roc_timer && aborted == (vif[0].mld ? 2 : 1));
        return 0;
    }
    if (fail_grant) {
        assert(!radio.state && !aborted);
        fail_grant = false;
        assert(!mt7925_remain_on_channel(NULL, &vif[1], NULL, 50, OFFCHANNEL));
    }
    assert(radio.state && !aborted);
    if (!strcmp(s, "other-vif")) {
        mt7925_mac_sta_event(NULL, &vif[1], &sta, MT76_STA_EVENT_AUTHORIZE);
        assert(radio.state && !aborted);
    }
    if (!strcmp(s, "tdls")) {
        sta.tdls = true;
        mt7925_mac_sta_event(NULL, &vif[0], &sta, MT76_STA_EVENT_AUTHORIZE);
        assert(radio.state && !aborted);
        sta.tdls = false;
    }
    if (!strcmp(s, "offchannel")) {
        mt7925_mac_sta_event(NULL, &vif[0], &sta, MT76_STA_EVENT_DISASSOC);
        assert(!mt7925_remain_on_channel(NULL, &vif[1], NULL, 50, OFFCHANNEL));
        device.phy.roc_timer = false;
        mt7925_roc_work(&device.phy.roc_work);
        assert(!radio.state && expired == 1);
        return 0;
    }
    if (!strcmp(s, "removed")) {
        /* The station-removal path already holds the device mutex. */
        mt792x_mutex_acquire(&device);
        mt7925_roc_abort_sync(&device);
        mt792x_mutex_release(&device);
        assert(!radio.state && !device.phy.roc_timer);
        assert(!mt7925_remain_on_channel(NULL, &vif[0], NULL, 50, OFFCHANNEL));
    }
    if (!strcmp(s, "expired")) {
        device.phy.roc_timer = false;
        mt7925_roc_work(&device.phy.roc_work);
        assert(!radio.state && !expired);
        assert(!mt7925_remain_on_channel(NULL, &vif[0], NULL, 50, OFFCHANNEL));
    }
    if (!strcmp(s, "queued")) {
        /* An expired timer worker may already be running, waiting for the mutex. */
        worker_running = true;
        device.phy.roc_timer = false;
        mt7925_mac_sta_event(NULL, &vif[0], &sta, MT76_STA_EVENT_AUTHORIZE);
        assert(!mt7925_remain_on_channel(NULL, &vif[1], NULL, 50, OFFCHANNEL));
        if (worker_running)
            mt7925_roc_work(&device.phy.roc_work);
        assert(radio.state && device.phy.roc_timer && !expired);
        return 0;
    }

    int previous = aborted;
    mt7925_mac_sta_event(NULL, &vif[0], &sta, !strcmp(s, "disassoc") ?
                         MT76_STA_EVENT_DISASSOC : MT76_STA_EVENT_AUTHORIZE);
    if (busy || !strcmp(s, "expired") || !strcmp(s, "failed") || !strcmp(s, "removed")) {
        assert(radio.state && device.phy.roc_timer && aborted == previous);
        mt7925_cancel_remain_on_channel(NULL, &vif[busy || !strcmp(s, "failed") ? 1 : 0]);
        assert(!radio.state && !device.phy.roc_timer);
    } else {
        assert(!radio.state && !device.phy.roc_timer && aborted == previous + 1);
    }
}
