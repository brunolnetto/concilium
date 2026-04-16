#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para extrair esquema e relacionamentos das planilhas AGIS
"""
import pandas as pd
import openpyxl
from openpyxl import load_workbook
import json
from pathlib import Path

# Caminhos
planejamento_file = r"C:\Users\GustavoArruda\Mendes Lobo\TI - Documentos\IA\planilha_investimento\2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsx"
relacionamentos_file = r"C:\Users\GustavoArruda\Mendes Lobo\TI - Documentos\IA\planilha_investimento\Relacionamentos_Tabelas.xlsx"

print("=" * 80)
print("ANÁLISE DE ESQUEMA - PLANILHA AGIS")
print("=" * 80)

# 1. Extrair nomes das abas do arquivo principal
print("\n[1] ABAS DA PLANILHA DE PLANEJAMENTO:")
print("-" * 80)
try:
    wb_plan = load_workbook(planejamento_file)
    abas_plan = wb_plan.sheetnames
    print(f"Total de abas: {len(abas_plan)}")
    for i, aba in enumerate(abas_plan, 1):
        print(f"  {i:2d}. {aba}")
except Exception as e:
    print(f"❌ Erro ao ler {planejamento_file}: {e}")

# 2. Extrair relacionamentos da segunda planilha
print("\n[2] RELACIONAMENTOS E DESCRIÇÕES:")
print("-" * 80)
try:
    wb_rel = load_workbook(relacionamentos_file, data_only=True)
    print(f"Abas em Relacionamentos: {wb_rel.sheetnames}")
    
    # Ler primeira aba que contiver dados
    for sheet_name in wb_rel.sheetnames:
        ws = wb_rel[sheet_name]
        print(f"\n  Aba: {sheet_name}")
        
        # Tentar ler como DataFrame
        df = pd.read_excel(relacionamentos_file, sheet_name=sheet_name)
        print(f"  Dimensões: {df.shape}")
        print(f"  Colunas: {list(df.columns)}")
        
        if not df.empty:
            print(f"\n  Primeiras linhas:")
            print(df.head(10).to_string())
        
except Exception as e:
    print(f"❌ Erro ao ler {relacionamentos_file}: {e}")

# 3. Estrutura detalhada de cada aba
print("\n[3] ESTRUTURA DAS ABAS (Primeiras 5 linhas e colunas):")
print("-" * 80)
try:
    for aba in abas_plan[:5]:  # Primeiras 5 abas
        print(f"\n  📄 ABA: {aba}")
        try:
            df = pd.read_excel(planejamento_file, sheet_name=aba, nrows=5, header=None)
            print(f"     Dimensões: {df.shape}")
            print(f"     Primeiras 3 colunas:")
            print(df.iloc[:, :3].to_string())
        except Exception as e:
            print(f"     ⚠️ Erro ao ler: {e}")
            
except Exception as e:
    print(f"❌ Erro geral: {e}")

print("\n" + "=" * 80)
print("FIM DA ANÁLISE")
print("=" * 80)
