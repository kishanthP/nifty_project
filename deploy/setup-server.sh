#!/usr/bin/env bash
# Run ONCE on a new Ubuntu server (Oracle Cloud), in the project folder:
#     bash deploy/setup-server.sh
#
# Installs Docker and opens the web ports (80 and 443) in the server's firewall.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

# Oracle's Ubuntu images block every port except SSH (22) with iptables.
# Allow HTTP and HTTPS, placed before the final "reject everything" rule.
for port in 80 443; do
    if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        reject_line="$(sudo iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
        if [[ -n "$reject_line" ]]; then
            sudo iptables -I INPUT "$reject_line" -p tcp --dport "$port" -j ACCEPT
        else
            sudo iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        fi
    fi
done
# Keep the rules after a reboot.
if command -v netfilter-persistent >/dev/null 2>&1; then
    sudo netfilter-persistent save
else
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
    sudo netfilter-persistent save
fi

mkdir -p backups

echo
echo "Server is ready. Log out and log in again (type: exit), so docker works without sudo."
