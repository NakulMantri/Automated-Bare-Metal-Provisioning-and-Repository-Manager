#!/usr/bin/env bash

# Local Continuous Integration and Syntax Verification script
# Enforces formatting, linting rules, and tests across all components.

set -e

# ANSI styling codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}${BOLD}=== Starting Automation CI/CD Validation Pipeline ===${NC}\n"

FAILURES=0

# 1. Verify Ansible Syntax
echo -e "${BLUE}1. Validating Ansible Playbook Syntax...${NC}"
if command -v ansible-playbook &> /dev/null; then
    if ansible-playbook --syntax-check ansible/site.yml; then
        echo -e "${GREEN}✔ Ansible playbook syntax check passed.${NC}\n"
    else
        echo -e "${RED}❌ Ansible playbook syntax check failed!${NC}\n"
        ((FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠ ansible-playbook not found. Skipping syntax check.${NC}\n"
fi

# 2. Run Shellcheck on Bash scripts
echo -e "${BLUE}2. Linting Shell Scripts (shellcheck)...${NC}"
if command -v shellcheck &> /dev/null; then
    if shellcheck scripts/*.sh; then
        echo -e "${GREEN}✔ Shell script linting passed.${NC}\n"
    else
        echo -e "${RED}❌ Shell script linting failed!${NC}\n"
        ((FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠ shellcheck not found. Skipping shell script linting.${NC}\n"
fi

# 3. Verify Python Code Style with Black
echo -e "${BLUE}3. Checking Python Formatting Style (black)...${NC}"
if command -v black &> /dev/null; then
    if black --check src/; then
        echo -e "${GREEN}✔ Python code style matches formatting guidelines.${NC}\n"
    else
        echo -e "${RED}❌ Python code formatting checks failed! Run 'black src/' to resolve.${NC}\n"
        ((FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠ black code formatter not found. Skipping style checks.${NC}\n"
fi

# 4. Lint Python Code with Flake8
echo -e "${BLUE}4. Linting Python Source Code (flake8)...${NC}"
if command -v flake8 &> /dev/null; then
    # Exclude tests and check code quality
    if flake8 src/ --count --select=E9,F63,F7,F82 --show-source --statistics; then
        echo -e "${GREEN}✔ Python code syntax linting passed.${NC}\n"
    else
        echo -e "${RED}❌ Python linting found critical errors!${NC}\n"
        ((FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠ flake8 linter not found. Skipping code quality linting.${NC}\n"
fi

# 5. Execute Pytest Unit Tests
echo -e "${BLUE}5. Running Unit and Integration Tests (pytest)...${NC}"
if command -v pytest &> /dev/null; then
    # Ensure src is in python path
    export PYTHONPATH=src
    if pytest; then
        echo -e "${GREEN}✔ All unit tests passed.${NC}\n"
    else
        echo -e "${RED}❌ Pytest suite failed!${NC}\n"
        ((FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠ pytest not found. Skipping automated unit tests.${NC}\n"
fi

# 6. Final Status Report
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✔ SUCCESS: All integration validation checks passed!${NC}"
    exit 0
else
    echo -e "${RED}${BOLD}❌ FAILURE: $FAILURES validation checks failed! Resolve errors before commit integration.${NC}"
    exit 1
fi
