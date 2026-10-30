#!/bin/bash -e

install -d "${ROOTFS_DIR}/opt/photobox"
install -m 0644 "${SUB_STAGE_DIR}/files/photobox.whl" "${ROOTFS_DIR}/opt/photobox/photobox.whl"
install -D -m 0644 \
	"${SUB_STAGE_DIR}/files/photobox.service" \
	"${ROOTFS_DIR}/etc/systemd/system/photobox.service"
install -D -m 0644 \
	"${SUB_STAGE_DIR}/files/photobox-regulatory-domain.service" \
	"${ROOTFS_DIR}/etc/systemd/system/photobox-regulatory-domain.service"
install -D -m 0644 \
	"${SUB_STAGE_DIR}/files/50-photobox-network.rules" \
	"${ROOTFS_DIR}/etc/polkit-1/rules.d/50-photobox-network.rules"
