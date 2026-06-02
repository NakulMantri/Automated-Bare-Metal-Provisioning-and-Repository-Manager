FROM rockylinux:9

# Install core packaging utilities and build chains
RUN dnf install -y \
    rpm-build \
    rpmsign \
    createrepo_c \
    gpg \
    make \
    gcc \
    findutils \
    tar \
    unzip \
    && dnf clean all

# Create directories mapping the workspace layout
WORKDIR /workspace

# Set default entrypoint
CMD ["/bin/bash"]
