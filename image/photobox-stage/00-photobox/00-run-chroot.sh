python3 -m venv /opt/photobox/venv
/opt/photobox/venv/bin/pip install --no-cache-dir /opt/photobox/photobox.whl
rm /opt/photobox/photobox.whl
groupadd --system photobox
useradd --system --gid photobox --home-dir /var/lib/photobox --create-home \
	--shell /usr/sbin/nologin --groups video photobox
chmod 0700 /var/lib/photobox
mkdir -p /etc/photobox
chown root:photobox /etc/photobox
chmod 0750 /etc/photobox
mkdir -p /etc/systemd/system/multi-user.target.wants
ln -s /etc/systemd/system/photobox.service /etc/systemd/system/multi-user.target.wants/photobox.service
