#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Data Management Skill for AGIS Planning Spreadsheet

Manages foundational data tables:
- DADOS: Unit costs and recurring expenses
- PRODUÇÕES: Activity production rates
- PRATICABILIDADE: Monthly weather-based productivity factor
- MÃO DE OBRA: Labor costs database
- EQUIPAMENTOS: Equipment costs database
- BDI: Business markup margins

Author: AGIS Planning System
Version: 1.0.0
"""

import pandas as pd
import openpyxl
from openpyxl import load_workbook
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import json
from datetime import datetime


@dataclass
class ValidationReport:
    """Data validation report"""
    status: str  # "PASS" or "FAIL"
    table_name: str
    errors: List[str]
    warnings: List[str]
    summary: str
    timestamp: str


class BaseDataSkill:
    """
    Skill for managing foundational data in AGIS planning spreadsheet
    """
    
    # Table definitions
    TABLE_DEFINITIONS = {
        "DADOS": {
            "description": "Custos unitários de equipamentos e funcionários por mês",
            "critical_columns": ["Descrição", "Tipo", "Valor/Mês"],
            "data_type": "cost_reference",
        },
        "PRODUÇÕES": {
            "description": "Definição de produção horária das fases",
            "critical_columns": ["Atividade", "Unidade", "Produção Horária"],
            "data_type": "production_reference",
        },
        "PRATICABILIDADE": {
            "description": "Fator de ocorrência pluviômetrica mensal",
            "critical_columns": ["Mês", "% Produtivo"],
            "data_type": "productivity_factor",
            "months": ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", 
                      "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"],
        },
        "MÃO DE OBRA": {
            "description": "Base de dados de funções e custos de mão de obra",
            "critical_columns": ["Função", "Salário"],
            "data_type": "reference_db",
            "exact_match_required": True,
        },
        "EQUIPAMENTOS": {
            "description": "Base de dados de custos de equipamentos",
            "critical_columns": ["Equipamento", "Valor Mensal"],
            "data_type": "reference_db",
            "exact_match_required": True,
        },
        "BDI": {
            "description": "Margem de lucro por tipo de custo",
            "critical_columns": ["Tipo Custo", "% BDI"],
            "data_type": "markup_factor",
        },
    }
    
    def __init__(self, spreadsheet_path: str):
        """
        Initialize skill with path to planning spreadsheet
        
        Args:
            spreadsheet_path: Path to 2026_03_30_PLANEJAMENTO_LOTE*.xlsx
        """
        self.spreadsheet_path = Path(spreadsheet_path)
        self.workbook = None
        self._validate_path()
    
    def _validate_path(self):
        """Validate that spreadsheet exists"""
        if not self.spreadsheet_path.exists():
            raise FileNotFoundError(f"Spreadsheet not found: {self.spreadsheet_path}")
    
    def load_table(self, table_name: str, header_row: int = 0) -> pd.DataFrame:
        """
        Load a table from the spreadsheet
        
        Args:
            table_name: Name of the sheet/table (e.g., "DADOS", "PRODUÇÕES")
            header_row: Row number containing headers (0-indexed)
        
        Returns:
            Pandas DataFrame with table data
        
        Raises:
            ValueError: If table not found or can't be read
        """
        if table_name not in self.TABLE_DEFINITIONS:
            raise ValueError(f"Unknown table: {table_name}. Valid tables: {list(self.TABLE_DEFINITIONS.keys())}")
        
        try:
            df = pd.read_excel(
                self.spreadsheet_path,
                sheet_name=table_name,
                header=header_row
            )
            
            # Clean up: remove completely empty rows/columns
            df = df.dropna(how='all')
            df = df.dropna(how='all', axis=1)
            
            return df
        
        except Exception as e:
            raise ValueError(f"Failed to load table '{table_name}': {str(e)}")
    
    def validate_data(self, df: pd.DataFrame, table_name: str) -> ValidationReport:
        """
        Validate data quality and consistency
        
        Args:
            df: DataFrame to validate
            table_name: Name of table for context
        
        Returns:
            ValidationReport with status and findings
        """
        errors = []
        warnings = []
        
        # Check: Empty DataFrame
        if df.empty:
            errors.append(f"Table '{table_name}' is empty")
        
        # Check: Null values in critical columns
        if table_name in self.TABLE_DEFINITIONS:
            critical_cols = self.TABLE_DEFINITIONS[table_name].get("critical_columns", [])
            for col in critical_cols:
                if col in df.columns:
                    null_count = df[col].isna().sum()
                    if null_count > 0:
                        errors.append(f"Column '{col}' has {null_count} null values")
        
        # Check: Duplicates in reference tables
        if table_name in ["MÃO DE OBRA", "EQUIPAMENTOS"]:
            if "Função" in df.columns or "Equipamento" in df.columns:
                key_col = "Função" if "Função" in df.columns else "Equipamento"
                duplicates = df[key_col].duplicated().sum()
                if duplicates > 0:
                    errors.append(f"Column '{key_col}' has {duplicates} duplicate entries")
        
        # Check: Numeric columns have valid values
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            # Check for negative values in cost/percentage columns
            if any(keyword in col for keyword in ['Valor', 'Custo', '%']):
                negatives = (df[col] < 0).sum()
                if negatives > 0:
                    warnings.append(f"Column '{col}' has {negatives} negative values")
            
            # Check for percentages > 100
            if '%' in col:
                over_100 = (df[col] > 100).sum()
                if over_100 > 0:
                    warnings.append(f"Column '{col}' has {over_100} values > 100%")
        
        # Check: Special case - PRATICABILIDADE monthly alignment
        if table_name == "PRATICABILIDADE":
            expected_months = self.TABLE_DEFINITIONS["PRATICABILIDADE"]["months"]
            # Would need to check actual columns C-N
            if df.shape[1] < 12:
                warnings.append("PRATICABILIDADE may be missing monthly columns (expected 12)")
        
        # Determine overall status
        status = "FAIL" if errors else "PASS" if not warnings else "WARNING"
        
        # Build summary
        summary = f"{table_name}: "
        if status == "FAIL":
            summary += f"{len(errors)} critical errors"
        elif status == "WARNING":
            summary += f"{len(warnings)} warnings"
        else:
            summary += "All checks passed ✓"
        
        return ValidationReport(
            status=status,
            table_name=table_name,
            errors=errors,
            warnings=warnings,
            summary=summary,
            timestamp=datetime.now().isoformat()
        )
    
    def sync_references(self, source_table: str, target_table: str) -> Dict[str, Any]:
        """
        Validate reference name matching between tables
        
        Critical for exact name matching in:
        - MÃO DE OBRA → EQUIPE, ADM, TOP, LAB, QSMS
        - EQUIPAMENTOS → EQUIPE, ADM, MOB
        
        Args:
            source_table: Reference table (source of truth)
            target_table: Table being updated
        
        Returns:
            Dictionary with sync status, mismatches, suggestions
        """
        try:
            source_df = self.load_table(source_table)
            target_df = self.load_table(target_table)
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Failed to load tables: {str(e)}",
                "mismatches": []
            }
        
        # Identify key column in source
        if source_table == "MÃO DE OBRA":
            source_col = "Função"
        elif source_table == "EQUIPAMENTOS":
            source_col = "Equipamento"
        else:
            source_col = source_df.columns[0]
        
        # Identify where source names are referenced in target
        mismatches = []
        found = 0
        
        # Look for the names used in target
        for target_col in target_df.columns:
            source_values = set(source_df[source_col].dropna().astype(str))
            target_values = set(target_df[target_col].dropna().astype(str))
            
            # Check for intersection
            if source_values & target_values:
                found += len(source_values & target_values)
            
            # Find mismatches (names in target that don't exist in source)
            missing = target_values - source_values
            if missing:
                for value in missing:
                    mismatches.append({
                        "in_target": value,
                        "not_in_source": source_table,
                        "suggestion": self._find_closest_match(value, source_values)
                    })
        
        status = "OK" if not mismatches else "MISMATCH"
        
        return {
            "status": status,
            "source_table": source_table,
            "target_table": target_table,
            "found_matches": found,
            "mismatches": mismatches,
            "message": f"Found {found} matches, {len(mismatches)} mismatches"
        }
    
    def _find_closest_match(self, value: str, candidates: set, threshold: float = 0.8) -> Optional[str]:
        """
        Find closest matching string from candidates using difflib-like logic
        
        Args:
            value: String to match
            candidates: Set of candidate strings
            threshold: Similarity threshold (0-1)
        
        Returns:
            Closest match or None
        """
        from difflib import SequenceMatcher
        
        best_match = None
        best_ratio = threshold
        
        for candidate in candidates:
            ratio = SequenceMatcher(None, value.lower(), candidate.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        
        return best_match
    
    def export_table(self, df: pd.DataFrame, table_name: str, 
                    format: str = "xlsx", output_path: Optional[str] = None) -> str:
        """
        Export table to file
        
        Args:
            df: DataFrame to export
            table_name: Name for reference
            format: Format ("xlsx", "csv", "json")
            output_path: Custom output path (optional)
        
        Returns:
            Path to exported file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = self.spreadsheet_path.parent / "exports"
            output_dir.mkdir(exist_ok=True)
            
            if format == "xlsx":
                output_path = output_dir / f"{table_name}_{timestamp}.xlsx"
            elif format == "csv":
                output_path = output_dir / f"{table_name}_{timestamp}.csv"
            elif format == "json":
                output_path = output_dir / f"{table_name}_{timestamp}.json"
            else:
                raise ValueError(f"Unsupported format: {format}")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if format == "xlsx":
                df.to_excel(output_path, sheet_name=table_name, index=False)
            elif format == "csv":
                df.to_csv(output_path, index=False, encoding='utf-8-sig')
            elif format == "json":
                df.to_json(output_path, orient='records', force_ascii=False, indent=2)
            
            return str(output_path)
        
        except Exception as e:
            raise IOError(f"Failed to export table: {str(e)}")
    
    def validate_all(self) -> List[ValidationReport]:
        """
        Run validation on all 6 base tables
        
        Returns:
            List of ValidationReport objects
        """
        reports = []
        
        for table_name in self.TABLE_DEFINITIONS.keys():
            try:
                df = self.load_table(table_name)
                report = self.validate_data(df, table_name)
                reports.append(report)
            except Exception as e:
                reports.append(ValidationReport(
                    status="ERROR",
                    table_name=table_name,
                    errors=[f"Failed to load: {str(e)}"],
                    warnings=[],
                    summary=f"{table_name}: Load error",
                    timestamp=datetime.now().isoformat()
                ))
        
        return reports
    
    def generate_health_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report of all base data
        
        Returns:
            Dictionary with overall health status and details
        """
        reports = self.validate_all()
        
        passed = sum(1 for r in reports if r.status == "PASS")
        warnings = sum(1 for r in reports if r.status == "WARNING")
        failed = sum(1 for r in reports if r.status in ["FAIL", "ERROR"])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "HEALTHY" if failed == 0 else "DEGRADED" if warnings > 0 else "CRITICAL",
            "summary": f"{passed} PASS, {warnings} WARNING, {failed} FAIL",
            "details": [
                {
                    "table": r.table_name,
                    "status": r.status,
                    "errors_count": len(r.errors),
                    "warnings_count": len(r.warnings),
                    "errors": r.errors[:3],  # First 3 errors
                    "warnings": r.warnings[:3]  # First 3 warnings
                }
                for r in reports
            ]
        }


def main():
    """
    Example usage of BaseDataSkill
    """
    import sys
    
    # Adjust path as needed
    spreadsheet = r"C:\Users\GustavoArruda\Mendes Lobo\TI - Documentos\IA\planilha_investimento\2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsx"
    
    print("=" * 70)
    print("BASE DATA SKILL - Health Check")
    print("=" * 70)
    
    try:
        skill = BaseDataSkill(spreadsheet)
        
        # Generate health report
        report = skill.generate_health_report()
        
        print(f"\n⏱️  Timestamp: {report['timestamp']}")
        print(f"📊 Overall Status: {report['overall_status']}")
        print(f"📈 Summary: {report['summary']}\n")
        
        for detail in report['details']:
            status_icon = "✅" if detail['status'] == "PASS" else "⚠️" if detail['status'] == "WARNING" else "❌"
            print(f"{status_icon} {detail['table']:20s} | {detail['status']:8s} | "
                  f"Errors: {detail['errors_count']}, Warnings: {detail['warnings_count']}")
            
            if detail['errors']:
                for err in detail['errors']:
                    print(f"    ❌ {err}")
            if detail['warnings']:
                for warn in detail['warnings']:
                    print(f"    ⚠️  {warn}")
        
        print("\n" + "=" * 70)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
