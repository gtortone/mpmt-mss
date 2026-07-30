
- copy mpmt-mss.service in /etc/systemd/system

- reload systemd: `systemctl daemon-reload`

- enable and start mpmt-mss service:  `systemctl enable --now mpmt-mss`

**Note: in order to run mpmt-mss please be sure to turn off other ModBus services (e.g. mbusd, rc-tcp, ...)**

