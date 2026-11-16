# 4.3 Remote Firmware Update of Irrigation Nodes

The remote update capability, which was introduced in revision 2 of the platform and has since been extended (see 4.1), allows the cloud to deliver a new firmware image to a field unit through the site hub; the node, which may be in the middle of an irrigation cycle when the notification arrives, should only begin the procedure when it is safe to do so, i.e. the valve is closed and the battery level, as reported by the fuel gauge, is not below 40 % (devices on mains power are exempt from the battery check but not from the valve check).

Upon reception of the update notification on `gh/<site>/<node_id>/update` — whose payload carries `version`, `url`, `size` and `sha256` — the controller compares the offered version against the running one and the notification is discarded if it is not strictly greater, in which case `REJECTED_VERSION` should be reported on the status topic. Downloading of the image into `fw_slot_b` is then performed in 512 KiB chunks over the hub's HTTP proxy, with each chunk being retried up to 3 times; should the retries be exhausted the unit reports `FAILED_DOWNLOAD`, erases the slot and continues to run the current image. The whole download has to complete within 30 minutes.

| Phase | Behaviour |
|---|---|
| Verification | Once the download has been completed the SHA-256 of the slot content is compared with `sha256` from the notification and the image signature is validated against the vendor key (Ed25519) before the slot is marked bootable; a gateway-side pre-check of the checksum also exists, so that corrupted images are normally never offered to devices, although this cannot be relied upon when the hub runs firmware older than 3.2. A failure of either check results in `FAILED_VERIFY` being reported and the slot being erased. |
| Activation | The node reboots into `fw_slot_b` only when no irrigation cycle is scheduled within the next 10 minutes; after the reboot the new image has to publish a `status` message carrying the new version within 120 s, otherwise the bootloader reverts to `fw_slot_a` on the next watchdog reset and `ROLLED_BACK` is reported by the old image. |
| Timeouts | Download: 45 min overall (the hub closes the proxy session after this time). Activation confirmation: 120 s. |

Note that the hub must be upgraded first where its version is lower than 3.2, and that the update notification is retained by the broker so that sleeping units receive it when they wake up, which could be up to 6 hours later.
