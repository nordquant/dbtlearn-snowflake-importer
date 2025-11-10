#!/bin/bash
set -euo pipefail

# Configuration
REGISTRY="registry.nordquant.com"
IMAGE_NAME="dbt-bootcamp-setup"
PLATFORMS="linux/amd64,linux/arm64"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
BUILD_ONLY=false
PUSH_ONLY=false
TAG="latest"

while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --push-only)
            PUSH_ONLY=true
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --platform)
            PLATFORMS="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Build and push multi-platform Docker images"
            echo ""
            echo "Options:"
            echo "  --build-only          Only build, don't push"
            echo "  --push-only           Only push existing image"
            echo "  --tag TAG             Tag to use (default: latest)"
            echo "  --platform PLATFORMS  Platforms to build for (default: linux/amd64,linux/arm64)"
            echo "  -h, --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Build and push for both platforms"
            echo "  $0 --build-only                       # Build only, don't push"
            echo "  $0 --tag v1.0.0                      # Build and push with custom tag"
            echo "  $0 --platform linux/amd64            # Build only for amd64"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${TAG}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if buildx is available
if ! docker buildx version > /dev/null 2>&1; then
    log_error "Docker buildx is not available. Please upgrade Docker."
    exit 1
fi

# Login check (only if we're going to push)
if [[ "$BUILD_ONLY" == false ]]; then
    log_info "Checking registry authentication..."

    # Try to get credentials from base-infra/.env
    ENV_FILE="../../base-infra/.env"
    if [[ -f "$ENV_FILE" ]]; then
        USERNAME=$(grep "^MASTER_USERNAME=" "$ENV_FILE" | cut -d'=' -f2)
        PASSWORD=$(grep "^MASTER_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2)

        if [[ -z "$USERNAME" ]]; then
            log_error "Could not find MASTER_USERNAME in $ENV_FILE"
            exit 1
        fi

        if [[ -z "$PASSWORD" ]]; then
            log_error "Could not find MASTER_PASSWORD in $ENV_FILE"
            exit 1
        fi
    else
        log_error "Could not find $ENV_FILE"
        log_error "Please ensure base-infra/.env exists with MASTER_USERNAME and MASTER_PASSWORD"
        exit 1
    fi

    # Check if already logged in
    if ! docker login "${REGISTRY}" --username "$USERNAME" --password-stdin < /dev/null 2>/dev/null; then
        log_warn "Not logged in to ${REGISTRY}"
        log_info "Attempting login with credentials from $ENV_FILE..."

        if echo "$PASSWORD" | docker login "${REGISTRY}" -u "$USERNAME" --password-stdin; then
            log_info "Successfully logged in to ${REGISTRY} as ${USERNAME}"
        else
            log_error "Failed to login to ${REGISTRY}"
            exit 1
        fi
    else
        log_info "Already logged in to ${REGISTRY}"
    fi
fi

# Build and push
if [[ "$PUSH_ONLY" == true ]]; then
    log_info "Pushing existing image: ${FULL_IMAGE_NAME}"
    docker push "${FULL_IMAGE_NAME}"
else
    log_info "Building for platforms: ${PLATFORMS}"
    log_info "Image: ${FULL_IMAGE_NAME}"

    BUILD_ARGS=(
        "buildx"
        "build"
        "--platform" "${PLATFORMS}"
        "-t" "${FULL_IMAGE_NAME}"
    )

    if [[ "$BUILD_ONLY" == false ]]; then
        BUILD_ARGS+=("--push")
        log_info "Build and push mode enabled"
    else
        BUILD_ARGS+=("--load")
        log_info "Build-only mode enabled (no push)"

        # Check if we're trying to build multiple platforms with --load
        if [[ "$PLATFORMS" == *","* ]]; then
            log_error "Cannot use --build-only with multiple platforms."
            log_error "Docker buildx cannot load multi-platform images to local Docker."
            log_error "Either:"
            log_error "  1. Remove --build-only to push to registry"
            log_error "  2. Use --platform with a single platform (e.g., --platform linux/arm64)"
            exit 1
        fi
    fi

    BUILD_ARGS+=(".")

    log_info "Running: docker ${BUILD_ARGS[*]}"
    docker "${BUILD_ARGS[@]}"
fi

# Verify
if [[ "$BUILD_ONLY" == false ]]; then
    log_info "Verifying image in registry..."
    docker pull "${FULL_IMAGE_NAME}" > /dev/null 2>&1

    # Get image info
    IMAGE_SIZE=$(docker images "${FULL_IMAGE_NAME}" --format "{{.Size}}")
    log_info "Image successfully pushed!"
    log_info "Image: ${FULL_IMAGE_NAME}"
    log_info "Size: ${IMAGE_SIZE}"
    log_info "Platforms: ${PLATFORMS}"
fi

log_info "Done!"
