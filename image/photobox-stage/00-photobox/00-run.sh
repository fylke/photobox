#!/bin/bash -e

install -d "${ROOTFS_DIR}/opt/photobox"
install -m 0644 "${SUB_STAGE_DIR}/files/photobox.whl" "${ROOTFS_DIR}/opt/photobox/photobox.whl"
install -D -m 0644 \
	"${SUB_STAGE_DIR}/files/photobox.service" \
	"${ROOTFS_DIR}/etc/systemd/system/photobox.service"
