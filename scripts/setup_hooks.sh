#!/usr/bin/env bash

# Diretório raiz do projeto
PROJECT_ROOT=$(git rev-parse --show-toplevel)

# Pasta de hooks customizados
HOOKS_DIR="$PROJECT_ROOT/scripts/githooks"

# Caminho para o diretório de hooks do git
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

# Tornar todos os scripts em scripts/githooks executáveis
chmod +x "$HOOKS_DIR"/*

# Criar um symlink dos nossos hooks para dentro da pasta do git
ln -sf "$HOOKS_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"
ln -sf "$HOOKS_DIR/pre-push" "$GIT_HOOKS_DIR/pre-push"

echo "✅ Git hooks configurados com sucesso!"
echo "Commits diretos nas branches 'main' e 'develop' agora serão bloqueados."
