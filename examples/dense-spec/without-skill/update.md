# 4.3 Remote Firmware Update of Irrigation Nodes (node-side client)

This section tells you how to build the update client that runs on the node. The cloud sends a new firmware image to a node through the site hub. The node downloads it, verifies it, reboots into it, and confirms it works. If anything goes wrong, the node keeps running the old image and reports why.

Terms used below:

- **Node**: the field unit that runs your firmware.
- **Hub**: the site hub. It relays messages and proxies HTTP downloads for the node.
- **Slot A / slot B**: `fw_slot_a` holds the running image. `fw_slot_b` is where the new image is written.
- **Running version**: the firmware version of the image the node is executing now.

## 1. Interfaces

| Item | Value |
|---|---|
| Update notification topic (node subscribes) | `gh/<site>/<node_id>/update` |
| Status topic (node publishes) | `gh/<site>/<node_id>/status` (see open items 1) |
| Download transport | HTTP GET through the hub's HTTP proxy |
| Image signature | Ed25519, checked against the vendor public key |
| Image checksum | SHA-256 |

The notification payload has four fields:

| Field | Meaning |
|---|---|
| `version` | Version of the offered image |
| `url` | Where to download the image |
| `size` | Image size in bytes |
| `sha256` | Expected SHA-256 of the whole image |

The broker retains the notification. A node that was asleep receives it when it wakes, which can be up to 6 hours after it was sent. Treat every notification as possibly old, and always do the checks in section 2.

## 2. Procedure

Do the steps in this order. Every failure ends in "report a status, clean up, keep running slot A". Nothing in this procedure may stop the node from running its current image.

### Step 1. Check the version

Compare `version` with the running version. If `version` is not strictly greater, discard the notification and publish `REJECTED_VERSION`. Do nothing else. (Comparison rules: see open items 2.)

### Step 2. Wait until it is safe to start

Start the download only when both conditions are true:

- The irrigation valve is closed. This applies to every node.
- The battery level from the fuel gauge is 40 % or higher. Nodes on mains power skip this check.

If a condition is false, do not start. Keep the notification pending and check again later, for example after the current cycle ends. Do not publish a failure status for this wait. (Re-check interval: see open items 3.)

### Step 3. Download into slot B

1. Erase `fw_slot_b`.
2. Request the image from `url` through the hub's HTTP proxy, in chunks of 512 KiB (the last chunk may be smaller).
3. Write each chunk to `fw_slot_b` at its offset.
4. If a chunk fails, retry that chunk up to 3 times. If it still fails, stop. Publish `FAILED_DOWNLOAD`, erase `fw_slot_b`, and keep running slot A.
5. The whole download must finish within 30 minutes of starting. If it does not, handle it as `FAILED_DOWNLOAD`.

About the 30-minute limit: the original text gave both 30 and 45 minutes. The hub closes the proxy session at 45 minutes, so the node limit is set below that, to 30. See open items 4.

### Step 4. Verify

When the download is complete, in this order:

1. Compute the SHA-256 of the content in `fw_slot_b` and compare it with `sha256` from the notification.
2. Validate the image signature with the vendor Ed25519 key.

Mark the slot bootable only if both pass. If either fails, publish `FAILED_VERIFY`, erase `fw_slot_b`, and keep running slot A.

Always do both checks on the node. The cloud gateway also checks the checksum before offering an image, but that check is not reliable when the hub runs firmware older than 3.2. Never skip the node checks because of it.

### Step 5. Activate

Reboot into `fw_slot_b` only if no irrigation cycle is scheduled in the next 10 minutes. If one is, wait and check again. Do not reboot during or just before a cycle. (Re-check interval: see open items 3.)

### Step 6. Confirm after reboot

The new image must publish a `status` message that contains its new version within 120 seconds of booting.

- If it does, the update is done.
- If it does not, the bootloader switches back to `fw_slot_a` at the next watchdog reset. The old image then publishes `ROLLED_BACK`.

So the new image must start the status publisher early in boot, and must keep the watchdog running. Do not disable the watchdog to avoid a rollback. The old image, once it boots again, is responsible for publishing `ROLLED_BACK`.

## 3. Status codes

| Code | Published by | When |
|---|---|---|
| `REJECTED_VERSION` | Running image | Offered version is not strictly greater than the running version (step 1) |
| `FAILED_DOWNLOAD` | Running image | A chunk failed after 3 retries, or the 30-minute limit passed (step 3) |
| `FAILED_VERIFY` | Running image | SHA-256 or signature check failed (step 4) |
| `ROLLED_BACK` | Old image (slot A) after revert | New image did not confirm within 120 s (step 6) |

## 4. Timeouts and limits

| Item | Value |
|---|---|
| Battery threshold | 40 % (not applied on mains power) |
| Chunk size | 512 KiB |
| Retries per chunk | 3 |
| Whole download | 30 min on the node (hub proxy session closes at 45 min) |
| Quiet window before reboot | no irrigation scheduled in next 10 min |
| Confirmation after reboot | 120 s |
| Retained notification delay | up to 6 h |

## 5. Dependencies outside the node

The hub must run firmware 3.2 or newer before nodes are updated. If the hub is older, it must be upgraded first. This is an operations step done by the cloud side, not by your client. It matters to you because on an older hub, corrupt images can reach the node, so your verification in step 4 is the only protection.

## Open items

The source text did not settle these. The choices below are what this rewrite assumes. Confirm them with the spec author and update this section.

1. **Status topic and payload.** The source says "the status topic" and "a `status` message carrying the new version" without a topic name or format. Assumed topic `gh/<site>/<node_id>/status`. The payload format (field names for the code and for the version) is not defined and must be agreed with the cloud team.
2. **Version comparison.** "Strictly greater" is not defined. Assumed semantic versioning (major.minor.patch, numeric comparison per part). Confirm.
3. **Re-check timing.** The source does not say how often to retry when the node is not safe to start or to reboot. Suggested: re-check when a cycle ends and at least every 5 minutes. Confirm.
4. **Download timeout.** The source said 30 minutes in one place and 45 in another. This text uses 30 min for the node, with the hub's 45 min as the outer limit.
5. **Slot erase on rollback and on retained re-delivery.** If the node reboots with the same notification still retained, step 1 discards it as "not strictly greater" once the update has succeeded. After `ROLLED_BACK` or a failure, the same notification will be seen again and would be retried. Whether to retry or to remember the failure is not specified. Assumed: retry on the next delivery, no failure memory.
6. **Failure status when the node is not safe.** No code exists for "deferred". Assumed that none is published.
7. **Image size check.** `size` is in the notification but the source does not say what to do with it. Assumed: reject with `FAILED_DOWNLOAD` if `size` exceeds the capacity of `fw_slot_b`, and treat a downloaded length different from `size` as `FAILED_DOWNLOAD`.
