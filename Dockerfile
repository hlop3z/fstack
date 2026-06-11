# Infra console (spike): the whole operator toolchain in one image.
# Image = toolchain. Mounts = state. Container = ephemeral.
# Contains NO secrets, NO keys, NO inventory, NO repo content — safe to push to a registry.

# python:3.12-slim, digest-pinned (multi-arch manifest list, fetched 2026-06-10)
FROM python@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Toolchain pins — this file is the single version surface for the operator stack.
RUN pip install --no-cache-dir \
    ansible-core==2.18.6 \
    fastapi==0.115.12 \
    uvicorn==0.34.2

# Collections ansible-core doesn't bundle but the target repo's playbooks use
# (community.general: ufw; ansible.posix: sysctl, mount; community.sops: secret vars).
RUN ansible-galaxy collection install \
    'community.general:>=10.0.0,<12.0.0' \
    'ansible.posix:>=1.6.0,<3.0.0' \
    'community.sops:>=2.0.0,<3.0.0'

# sops + age + kubectl, pinned (secret ops and read-only cluster checks)
RUN curl -fsSL -o /usr/local/bin/sops https://github.com/getsops/sops/releases/download/v3.13.1/sops-v3.13.1.linux.amd64 \
    && curl -fsSL https://github.com/FiloSottile/age/releases/download/v1.3.1/age-v1.3.1-linux-amd64.tar.gz | tar xz -C /tmp \
    && mv /tmp/age/age /tmp/age/age-keygen /usr/local/bin/ \
    && curl -fsSL -o /usr/local/bin/kubectl https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl \
    && chmod +x /usr/local/bin/sops /usr/local/bin/age /usr/local/bin/age-keygen /usr/local/bin/kubectl

ENV SOPS_AGE_KEY_FILE=/keys/age/keys.txt \
    KUBECONFIG=/kube/prod.yaml

COPY console/ /opt/console/console/
ENV PYTHONPATH=/opt/console \
    PYTHONUNBUFFERED=1 \
    CONSOLE_TARGET_DIR=/work

WORKDIR /work

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["docker-entrypoint.sh"]
