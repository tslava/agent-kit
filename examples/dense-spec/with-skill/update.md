# Remote update of the node

> Source: spec.md, section 4.3, "Remote Firmware Update of Irrigation Nodes".

Reader and job: an embedded developer who is new to the project implements the update client on the node, without a call with the author.

Names are in `GLOSSARY.md`. Section 4 of the source (4.1) extends this feature. This document does not contain 4.1.

## 1. What the update client does

The cloud sends an update notification through the hub. The update client on the node downloads the new image from the hub. It verifies the new image, reboots into it, and reports the result. If the new image does not report in time, the bootloader goes back to the running image.

Source: 4.3, paragraphs 1 and 2.

## 2. When the node can start an update

The node must start an update only when the valve is closed. A node on a battery must also have a battery level of 40 % or more. A node on mains power does not need the battery check, but it needs the valve check.

The node can be in an irrigation cycle when the update notification arrives, so the valve can be open. The source does not say what the node does when a start condition fails. See open question Q1.

Source: 4.3, paragraph 1.

## 3. Procedure

Do these steps for each update notification. The update topic is `gh/<site>/<node_id>/update`.

### 3.1 Receive

1. Read `version`, `url`, `size` and `sha256` from the update notification.
2. If `version` is not strictly greater than the running version, report `REJECTED_VERSION` on the status topic. The node discards the update notification and stops.
3. Check the start conditions from section 2. If a condition fails, see Q1.

The source does not give the order of step 3 and step 2. See Q2.

Source: 4.3, paragraphs 1 and 2.

### 3.2 Download

1. Download the new image from `url` into `fw_slot_b`. Use chunks of 512 KiB over the HTTP proxy of the hub.
2. If a chunk fails, retry the chunk. Retry it up to 3 times.
3. If a chunk still fails after the 3 retries, report `FAILED_DOWNLOAD`.
4. Erase `fw_slot_b`.
5. Continue to run the running image.
6. Complete the whole download within the time limit in section 4.

Steps 4 and 5 follow step 3 only. Source: 4.3, paragraph 2.

### 3.3 Verify

1. Compare the SHA-256 of the content of `fw_slot_b` with `sha256` from the update notification. The values must be equal.
2. Validate the image signature against the vendor key.
3. If one check fails, report `FAILED_VERIFY` and erase `fw_slot_b`. The source does not say that the node then runs the running image, but `fw_slot_a` is unchanged.
4. If both checks pass, mark `fw_slot_b` bootable.

Do this verification on every update, also when the hub pre-check exists. See section 5.

Source: 4.3, table row "Verification".

### 3.4 Activate

1. If the schedule has an irrigation cycle within the next 10 minutes, wait. The source does not say how long or what happens next. See Q3.
2. If the schedule has no irrigation cycle within the next 10 minutes, reboot into `fw_slot_b`.

Source: 4.3, table row "Activation".

### 3.5 Confirm or roll back

1. In the new image, publish a `status` message with the new version. Do this within 120 s after the reboot.

If the new image does not publish in 120 s, the bootloader reverts to `fw_slot_a` on the next watchdog reset. After the revert, the image in `fw_slot_a` (the running image from before the update) reports `ROLLED_BACK`.

The source does not say what causes the watchdog reset. See Q4.

Source: 4.3, table row "Activation".

## 4. Numbers

| Item | Value | Source |
|---|---|---|
| Minimum battery level | 40 % (the node can start at exactly 40 %) | paragraph 1 |
| Chunk size | 512 KiB | paragraph 2 |
| Retries for each chunk | 3 | paragraph 2 |
| Time limit for the whole download | 30 minutes in paragraph 2, 45 minutes in the table | see Q5 |
| Free time before a reboot | 10 minutes without an irrigation cycle in the schedule | table, "Activation" |
| Time to confirm the new image | 120 s after the reboot | table, "Activation" and "Timeouts" |
| Retention of the update notification | The node can get it up to 6 hours late | final note |

The source says the hub closes the proxy session after the 45 minutes.

## 5. Hub version

The hub has a pre-check of the checksum, so the cloud normally does not offer a corrupted image. The pre-check is not reliable when the hub version is lower than 3.2.

If the hub version is lower than 3.2, the operator must upgrade the hub before the node. The source does not say who the operator is.

The broker keeps the update notification. A sleeping node receives it when it wakes up, up to 6 hours later.

The source calls the pre-check `gateway-side`. See Q6. Source: 4.3, table row "Verification" and the final note.

## 6. Status codes

| Code | When the node reports it | What the node does after it |
|---|---|---|
| `REJECTED_VERSION` | `version` is not strictly greater than the running version | Discards the update notification |
| `FAILED_DOWNLOAD` | A chunk still fails after the 3 retries | Erases `fw_slot_b`, runs the running image |
| `FAILED_VERIFY` | The checksum check or the signature check fails | Erases `fw_slot_b` |
| `ROLLED_BACK` | The bootloader reverted to `fw_slot_a` | The running image reports it |

The source does not give the format of the status message. See Q7.

## 7. Open questions

Each question has the place in the source. Until the author answers, the reader can use the assumption in the last column. Mark each assumption in the code.

| ID | Question | Source | Assumption |
|---|---|---|---|
| Q1 | What does the node do with an update notification when the valve is open or the battery level is low? Discard, wait or retry? | 4.3, p. 1 | None. Ask the author. |
| Q2 | Does the node check the start conditions before or after the version check? | 4.3, p. 1 and 2 | The version check comes first. |
| Q3 | If an irrigation cycle is near, how long does the node wait, and does it check again? | 4.3, table | None. Ask the author. |
| Q4 | What causes the watchdog reset when the new image runs but does not publish? Does the bootloader revert without it? | 4.3, table | None. Ask the author. |
| Q5 | Is the download limit 30 or 45 minutes? | 4.3, p. 2 and table | Use 30 minutes. It is the shorter value. |
| Q6 | Is the `gateway` the same thing as the hub? | 4.3, table | Yes. |
| Q7 | What is the name of the status topic, and what is the payload of a status message? | 4.3, p. 2 | None. Ask the author. |
| Q8 | The source says `should` for the start conditions and for the `REJECTED_VERSION` report. Is each one a requirement? | 4.3, p. 1 and 2 | Yes, each is a requirement. |
| Q9 | What does `size` do? Does the node compare it with the download? | 4.3, p. 2 | None. Ask the author. |
| Q10 | What does the node report when the download does not finish in time? | 4.3, p. 2 | None. Ask the author. |
| Q11 | Where are the image signature and the vendor key stored? | 4.3, table | None. Ask the author. |
| Q12 | Does "retried up to 3 times" mean 3 retries (4 tries) or 3 tries? | 4.3, p. 2 | 3 retries. |

## 8. Design problems in the source

The author can decide these. This rewrite does not change them.

- The node can wait up to 6 hours to receive an update notification, so the update topic can offer an old version.
- Two time limits for one download exist (Q5).
- The source uses two kinds of status output: status codes on the status topic, and a `status` message with the version. It does not say if they share one topic (Q7).
