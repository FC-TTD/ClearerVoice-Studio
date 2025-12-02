#!/bin/bash

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 显示帮助信息
show_help() {
    echo "Usage: $0 [environment] [options]"
    echo ""
    echo "Environments:"
    echo "  stage       Deploy to staging environment"
    echo "  prod        Deploy to production environment"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -c, --check    Run in check mode (dry run)"
    echo "  -v, --verbose  Enable verbose output"
    echo "  -d, --diff     Show differences before making changes"
}

# 初始化变量
ENV=""
CHECK=""
VERBOSE=""
DIFF=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--check)
            CHECK="--check"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -d|--diff)
            DIFF="--diff"
            shift
            ;;
        stage|prod)
            if [ -z "$ENV" ]; then
                ENV="$1"
            else
                echo -e "${RED}Error: Multiple environments specified${NC}"
                show_help
                exit 1
            fi
            shift
            ;;
        *)
            echo -e "${RED}Error: Unknown argument: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 检查是否指定了环境
if [ -z "$ENV" ]; then
    echo -e "${RED}Error: No environment specified${NC}"
    show_help
    exit 1
fi

# 构建 Ansible 命令
ANSIBLE_CMD="ansible-playbook -i ansible/inventory.yml"

# 添加额外选项
if [ -n "$VERBOSE" ]; then
    ANSIBLE_CMD="$ANSIBLE_CMD $VERBOSE"
fi

if [ -n "$CHECK" ]; then
    ANSIBLE_CMD="$ANSIBLE_CMD $CHECK"
fi

if [ -n "$DIFF" ]; then
    ANSIBLE_CMD="$ANSIBLE_CMD $DIFF"
fi

# 添加环境限制和标签
if [ "$ENV" = "stage" ]; then
    ANSIBLE_CMD="$ANSIBLE_CMD --limit stage --tags stage"
elif [ "$ENV" = "prod" ]; then
    ANSIBLE_CMD="$ANSIBLE_CMD --limit prod --tags prod"
fi

# 添加 playbook 文件
ANSIBLE_CMD="$ANSIBLE_CMD ansible/site.yml"

# 显示将要执行的命令
echo -e "${YELLOW}Executing: $ANSIBLE_CMD${NC}"

# 执行命令
ANSIBLE_STDOUT_CALLBACK=debug eval $ANSIBLE_CMD

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Deployment to $ENV completed successfully!${NC}"
else
    echo -e "${RED}Deployment failed!${NC}"
    exit 1
fi
