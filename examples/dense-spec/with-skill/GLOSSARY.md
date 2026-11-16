# Glossary

## Names

| Use | Not | Meaning |
|---|---|---|
| node | controller, unit, field unit, device, board | The field unit with the valve. It runs the update client. |
| hub | site hub, gateway | The site unit between the cloud and the nodes. It has an HTTP proxy. |
| cloud | | The back end that sends the update notification. |
| broker | | The message broker. It keeps the update notification for sleeping nodes. |
| update notification | notification | The message on the update topic. It offers a firmware image. |
| update topic | | The topic `gh/<site>/<node_id>/update`. |
| status topic | | The topic where the node reports status codes. The source does not give its name. |
| firmware image | firmware, binary | The file that holds the program of the node. |
| running image | current image, old image | The firmware image that the node runs before the update. It is in `fw_slot_a`. |
| new image | offered image | The firmware image that the node downloads in the update. It goes to `fw_slot_b`. |
| slot | partition | A flash area that holds one firmware image. |
| chunk | block, part | One piece of 512 KiB of the new image. |
| irrigation cycle | watering cycle | A scheduled run of the valve. |
| valve | | The irrigation valve that the node controls. |
| battery level | charge, battery state | The value that the fuel gauge reports, in percent. |
| fuel gauge | | The part that measures the battery level. |
| mains power | | A power supply that is not a battery. |
| bootloader | | The program that starts a slot after a reset. |
| watchdog reset | | A reset that the watchdog timer causes. |
| vendor key | | The Ed25519 key that validates the signature of the new image. |

## Verbs

check, read, compare, discard, report, download, retry, erase, mark, reboot, publish, validate, stop, continue, wait, complete
