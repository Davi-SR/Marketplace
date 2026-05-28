import os
import threading
from functools import lru_cache
import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


app = FastAPI(
    title="Odontogroup AIBI Backend API",
    description="API do Especialista de BI da Odontogroup para consultas de mercado com base nos dados da ANS",
    version="1.0.0"
)

cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
cors_allow_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()] or ["*"]

# Adiciona CORS para flexibilidade do Front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pega o caminho do banco da variável de ambiente (definida no .env) ou usa o padrão local
db_env = os.getenv("DB_URL", "banco_odontogroup.db")
# Remove prefixo se houver
if db_env.startswith("duckdb:///"):
    DB_PATH = db_env.replace("duckdb:///", "")
else:
    DB_PATH = db_env

if not os.path.exists(DB_PATH):
    print(f"Banco de dados '{DB_PATH}' não encontrado. Inicializando estrutura vazia...")
    # Abre em modo de leitura-escrita para inicializar o arquivo
    conn_init = duckdb.connect(DB_PATH, read_only=False)
    conn_init.execute("""
        CREATE TABLE IF NOT EXISTS gold_marketplace_odontogroup (
            ano_mes VARCHAR,
            regiao VARCHAR,
            uf VARCHAR,
            municipio VARCHAR,
            sexo VARCHAR,
            faixa_etaria VARCHAR,
            tipo_plano VARCHAR,
            nome_operadora VARCHAR,
            modalidade_operadora VARCHAR,
            classificacao_player VARCHAR,
            total_vidas_ativas INTEGER,
            total_vidas_aderidas INTEGER,
            total_vidas_canceladas INTEGER,
            populacao_regiao_2025 INTEGER
        )
    """)
    conn_init.close()

print(f"Carregando banco '{DB_PATH}' para memória para otimização extrema...")
db_conn = duckdb.connect(':memory:')
db_conn.execute("PRAGMA threads=8")
try:
    db_conn.execute(f"ATTACH '{DB_PATH}' AS disk_db (READ_ONLY)")
    db_conn.execute("CREATE TABLE gold_marketplace_odontogroup AS SELECT * FROM disk_db.gold_marketplace_odontogroup")
    db_conn.execute("DETACH disk_db")
    print("Banco carregado em memória com sucesso e arquivo liberado!")
except Exception as e:
    print(f"Erro ao carregar para memória (usando disco nativo): {e}")
    db_conn = duckdb.connect(DB_PATH, read_only=True)
    db_conn.execute("PRAGMA threads=8")
    db_conn.execute("PRAGMA enable_object_cache=true")
from typing import Optional

class ChatRequest(BaseModel):
    pergunta: str

class ChatResponse(BaseModel):
    resposta: str

def build_where_clause(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None) -> tuple[str, list]:
    conditions = []
    params = []
    if uf:
        conditions.append("UPPER(uf) = UPPER(?)")
        params.append(uf)
    if operadora and operadora.lower() != "todos":
        conditions.append("UPPER(nome_operadora) = UPPER(?)")
        params.append(operadora)
    if regiao:
        conditions.append("UPPER(regiao) = UPPER(?)")
        params.append(regiao)
    if municipio:
        conditions.append("UPPER(municipio) = UPPER(?)")
        params.append(municipio)
    if faixa_etaria:
        conditions.append("UPPER(faixa_etaria) = UPPER(?)")
        params.append(faixa_etaria)
    if sexo:
        conditions.append("UPPER(sexo) = UPPER(?)")
        params.append(sexo)
    
    where_str = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where_str, params

def build_odontogroup_where_clause(uf: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None) -> tuple[str, list]:
    conditions = ["nome_operadora LIKE '%ODONTOGROUP%'"]
    params = []
    if uf:
        conditions.append("UPPER(uf) = UPPER(?)")
        params.append(uf)
    if regiao:
        conditions.append("UPPER(regiao) = UPPER(?)")
        params.append(regiao)
    if municipio:
        conditions.append("UPPER(municipio) = UPPER(?)")
        params.append(municipio)
    if faixa_etaria:
        conditions.append("UPPER(faixa_etaria) = UPPER(?)")
        params.append(faixa_etaria)
    if sexo:
        conditions.append("UPPER(sexo) = UPPER(?)")
        params.append(sexo)
    
    where_str = "WHERE " + " AND ".join(conditions)
    return where_str, params

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Recebe uma pergunta em linguagem natural sobre os dados de planos de saúde odontológicos,
    passa a pergunta para o agente do Agno (que monta e executa consultas SQL usando DuckDB),
    e retorna a análise fundamentada e insights gerados em linguagem natural.
    """
    if not request.pergunta.strip():
        raise HTTPException(status_code=400, detail="A pergunta não pode estar vazia.")
        
    try:
        from agent import agent

        run_response = agent.run(request.pergunta)
        response_text = run_response.content if hasattr(run_response, 'content') else str(run_response)
        return ChatResponse(resposta=response_text)
    except Exception as e:
        print(f"Erro no processamento da pergunta pelo agente: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro ao processar a pergunta com o Agente de IA: {str(e)}")

@app.get("/api/dashboard/visao-geral")
@lru_cache(maxsize=128)
def dashboard_visao_geral(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        
        pop_query = f"SELECT SUM(populacao_regiao_2025::FLOAT) FROM (SELECT DISTINCT regiao, populacao_regiao_2025 FROM gold_marketplace_odontogroup {where_str})"
        pop_raw = db_conn.cursor().execute(pop_query, params).fetchone()[0]
        populacao = float(pop_raw) if pop_raw else 0.0

        ben_query = f"SELECT SUM(total_vidas_ativas::FLOAT) FROM gold_marketplace_odontogroup {where_str}"
        ben_raw = db_conn.cursor().execute(ben_query, params).fetchone()[0]
        beneficiarios = float(ben_raw) if ben_raw else 0.0

        op_query = f"SELECT COUNT(DISTINCT nome_operadora) FROM gold_marketplace_odontogroup {where_str}"
        op_raw = db_conn.cursor().execute(op_query, params).fetchone()[0]
        operadoras = int(op_raw) if op_raw else 0

        penetracao = round((beneficiarios / populacao * 100), 2) if populacao > 0 else 0

        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao, municipio, faixa_etaria, sexo)
        ben_query_odonto = f"SELECT SUM(total_vidas_ativas::FLOAT) FROM gold_marketplace_odontogroup {where_odonto}"
        ben_raw_odonto = db_conn.cursor().execute(ben_query_odonto, params_odonto).fetchone()[0]
        beneficiarios_odonto = float(ben_raw_odonto) if ben_raw_odonto else 0.0

        diff_percentual = round(((beneficiarios / beneficiarios_odonto) - 1) * 100, 1) if beneficiarios_odonto > 0 else 0.0
        diff_absoluta = beneficiarios - beneficiarios_odonto

        return {
            "populacao_estimada_2025": populacao,
            "numero_beneficiarios": beneficiarios,
            "operadoras_odontologicas": operadoras,
            "penetracao_odonto": penetracao,
            "comparativo_odontogroup": {
                "beneficiarios": beneficiarios_odonto,
                "diferenca_percentual": diff_percentual,
                "diferenca_absoluta": diff_absoluta
            }
        }
    except Exception as e:
        print(f"Erro ao buscar KPIs do dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados do dashboard: {str(e)}")

@app.get("/api/dashboard/beneficiarios-uf")
@lru_cache(maxsize=128)
def dashboard_beneficiarios_uf(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        query = f"SELECT uf, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_str} GROUP BY uf ORDER BY total DESC"
        
        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao, municipio, faixa_etaria, sexo)
        query_odonto = f"SELECT uf, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_odonto} GROUP BY uf"
        
        # Query for Top 5 Operadoras per UF
        query_top5 = f"""
        WITH Ranked AS (
            SELECT uf, nome_operadora, SUM(total_vidas_ativas) as total_vidas,
                   ROW_NUMBER() OVER (PARTITION BY uf ORDER BY SUM(total_vidas_ativas) DESC) as rn
            FROM gold_marketplace_odontogroup
            {where_str}
            GROUP BY uf, nome_operadora
        )
        SELECT uf, nome_operadora, total_vidas
        FROM Ranked
        WHERE rn <= 5
        """
        
        cursor = db_conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        rows_odonto = cursor.execute(query_odonto, params_odonto).fetchall()
        rows_top5 = cursor.execute(query_top5, params).fetchall()
            
        odonto_dict = {row[0]: row[1] for row in rows_odonto}
        
        # Group top 5 operadoras by UF
        top5_dict = {}
        for row in rows_top5:
            estado = row[0]
            nome = row[1]
            vidas = float(row[2] or 0)
            if estado not in top5_dict:
                top5_dict[estado] = []
            top5_dict[estado].append({"nome": nome, "beneficiarios": vidas})

        results = []
        for row in rows:
            estado = row[0]
            total = float(row[1] or 0)
            odonto_total = float(odonto_dict.get(estado, 0))
            diff_percentual = round(((total / odonto_total) - 1) * 100, 1) if odonto_total > 0 else None
            diff_absoluta = total - odonto_total
            
            results.append({
                "uf": estado,
                "total_beneficiarios": total,
                "odontogroup_beneficiarios": odonto_total,
                "diferenca_percentual": diff_percentual,
                "diferenca_absoluta": diff_absoluta,
                "top_operadoras": top5_dict.get(estado, [])
            })
            
        return results
    except Exception as e:
        print(f"Erro ao buscar beneficiários por UF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados de beneficiários por UF: {str(e)}")

@app.get("/api/dashboard/beneficiarios-regiao")
@lru_cache(maxsize=128)
def dashboard_beneficiarios_regiao(uf: Optional[str] = None, operadora: Optional[str] = None, regiao_filter: Optional[str] = Query(None, alias="regiao"), municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao_filter, municipio, faixa_etaria, sexo)
        query = f"SELECT regiao, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_str} GROUP BY regiao ORDER BY total DESC"
        
        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao_filter, municipio, faixa_etaria, sexo)
        query_odonto = f"SELECT regiao, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_odonto} GROUP BY regiao"
        
        # Query for Top 5 Operadoras per Regiao
        query_top5 = f"""
        WITH Ranked AS (
            SELECT regiao, nome_operadora, SUM(total_vidas_ativas) as total_vidas,
                   ROW_NUMBER() OVER (PARTITION BY regiao ORDER BY SUM(total_vidas_ativas) DESC) as rn
            FROM gold_marketplace_odontogroup
            {where_str}
            GROUP BY regiao, nome_operadora
        )
        SELECT regiao, nome_operadora, total_vidas
        FROM Ranked
        WHERE rn <= 5
        """
        
        cursor = db_conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        rows_odonto = cursor.execute(query_odonto, params_odonto).fetchall()
        rows_top5 = cursor.execute(query_top5, params).fetchall()
            
        odonto_dict = {row[0]: row[1] for row in rows_odonto}
        
        # Group top 5 operadoras by Regiao
        top5_dict = {}
        for row in rows_top5:
            regiao_val = row[0]
            nome = row[1]
            vidas = float(row[2] or 0)
            
            if regiao_val not in top5_dict:
                top5_dict[regiao_val] = []
                
            # Calcular a diferenca entre esta operadora e a odontogroup nesta mesma regiao
            odonto_total_regiao = float(odonto_dict.get(regiao_val, 0))
            diferenca_odonto = vidas - odonto_total_regiao
            
            top5_dict[regiao_val].append({
                "nome": nome, 
                "beneficiarios": vidas,
                "diferenca_odonto": diferenca_odonto
            })

        results = []
        for row in rows:
            regiao_val = row[0]
            total = float(row[1] or 0)
            odonto_total = float(odonto_dict.get(regiao_val, 0))
            diff_percentual = round(((total / odonto_total) - 1) * 100, 1) if odonto_total > 0 else None
            diff_absoluta = total - odonto_total
            
            results.append({
                "regiao": regiao_val,
                "total_beneficiarios": total,
                "odontogroup_beneficiarios": odonto_total,
                "diferenca_percentual": diff_percentual,
                "diferenca_absoluta": diff_absoluta,
                "top_operadoras": top5_dict.get(regiao_val, [])
            })
            
        return results
    except Exception as e:
        print(f"Erro ao buscar beneficiários por Região: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados de beneficiários por Região: {str(e)}")

@app.get("/api/dashboard/ranking-operadoras")
@lru_cache(maxsize=128)
def dashboard_ranking_operadoras(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        query = f"SELECT nome_operadora, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_str} GROUP BY nome_operadora HAVING SUM(total_vidas_ativas) > 0 ORDER BY total DESC LIMIT 100"
        rows = db_conn.cursor().execute(query, params).fetchall()
        
        return [
            {
                "operadora": row[0], 
                "total_beneficiarios": row[1],
                "is_odontogroup": "ODONTOGROUP" in str(row[0]).upper()
            } for row in rows
        ]
    except Exception as e:
        print(f"Erro ao buscar ranking de operadoras: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados do ranking de operadoras: {str(e)}")

@app.get("/api/dashboard/ranking-municipio")
@lru_cache(maxsize=128)
def dashboard_ranking_municipio(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        query = f"SELECT municipio, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_str} GROUP BY municipio HAVING SUM(total_vidas_ativas) > 0 ORDER BY total DESC LIMIT 100"
        
        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao, municipio, faixa_etaria, sexo)
        query_odonto = f"SELECT municipio, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_odonto} GROUP BY municipio"

        cursor = db_conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        rows_odonto = cursor.execute(query_odonto, params_odonto).fetchall()
            
        odonto_dict = {row[0]: row[1] for row in rows_odonto}
        
        results = []
        for row in rows:
            mun = row[0]
            total = float(row[1] or 0)
            odonto_total = float(odonto_dict.get(mun, 0))
            diff_percentual = round(((total / odonto_total) - 1) * 100, 1) if odonto_total > 0 else None
            diff_absoluta = total - odonto_total
            
            results.append({
                "municipio": mun, 
                "total_beneficiarios": total,
                "odontogroup_beneficiarios": odonto_total,
                "diferenca_percentual": diff_percentual,
                "diferenca_absoluta": diff_absoluta
            })
            
        return results
    except Exception as e:
        print(f"Erro ao buscar ranking de municipio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados do ranking de municipio: {str(e)}")

@app.get("/api/dashboard/ranking-regiao")
@lru_cache(maxsize=128)
def dashboard_ranking_regiao(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        query = f"""
            SELECT regiao, 
                   MAX(populacao_regiao_2025) as pop, 
                   SUM(total_vidas_ativas) as total 
            FROM gold_marketplace_odontogroup
            {where_str}
            GROUP BY regiao 
            ORDER BY total DESC
        """
        
        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao, municipio, faixa_etaria, sexo)
        query_odonto = f"SELECT regiao, SUM(total_vidas_ativas) as total FROM gold_marketplace_odontogroup {where_odonto} GROUP BY regiao"
        
        cursor = db_conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        rows_odonto = cursor.execute(query_odonto, params_odonto).fetchall()
            
        odonto_dict = {row[0]: row[1] for row in rows_odonto}

        results = []
        for row in rows:
            r_name = row[0]
            pop = float(row[1] or 0)
            total = float(row[2] or 0)
            odonto_total = float(odonto_dict.get(r_name, 0))
            diff_percentual = round(((total / odonto_total) - 1) * 100, 1) if odonto_total > 0 else None
            diff_absoluta = total - odonto_total

            results.append({
                "regiao": r_name,
                "populacao": pop,
                "beneficiarios": total,
                "odontogroup_beneficiarios": odonto_total,
                "diferenca_percentual": diff_percentual,
                "diferenca_absoluta": diff_absoluta
            })
            
        return results
    except Exception as e:
        print(f"Erro ao buscar ranking de região: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no ranking por região: {str(e)}")

@app.get("/api/dashboard/filtros-operadoras")
@lru_cache(maxsize=128)
def dashboard_filtros_operadoras(uf: Optional[str] = None, regiao: Optional[str] = None, municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, None, regiao, municipio, faixa_etaria, sexo)
        query = f"SELECT DISTINCT nome_operadora FROM gold_marketplace_odontogroup {where_str} ORDER BY nome_operadora ASC"
        rows = db_conn.cursor().execute(query, params).fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"Erro ao buscar filtro de operadoras: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no filtro de operadoras: {str(e)}")

@app.get("/api/health")
def health_check():
    """
    Retorna o status de saúde da aplicação e valida se a conexão com o DuckDB está operacional.
    """
    try:
        # Teste rápido de query
        db_conn.execute("SELECT 1")
        db_status = "operacional"
        table_rows = db_conn.execute("SELECT COUNT(*) FROM gold_marketplace_odontogroup").fetchone()[0]
    except Exception as e:
        db_status = f"erro: {str(e)}"
        table_rows = None
        
    return {
        "status": "healthy",
        "duckdb_status": db_status,
        "database_file": DB_PATH,
        "database_exists": os.path.exists(DB_PATH),
        "gold_marketplace_odontogroup_rows": table_rows
    }

@app.on_event("shutdown")
def shutdown_event():
    """
    Garante que a conexão global com o DuckDB seja encerrada corretamente ao desligar a API.
    """
    try:
        db_conn.close()
        print("Conexão com o DuckDB encerrada com sucesso.")
    except Exception as e:
        print(f"Erro ao fechar conexão com o DuckDB: {str(e)}")


@app.get("/api/dashboard/faixa-etaria")
@lru_cache(maxsize=128)
def dashboard_faixa_etaria(uf: Optional[str] = None, operadora: Optional[str] = None, regiao: Optional[str] = Query(None, alias="regiao"), municipio: Optional[str] = None, faixa_etaria: Optional[str] = None, sexo: Optional[str] = None):
    try:
        where_str, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)
        
        # Calculate true population for the filtered region using the exact same logic as visao-geral
        pop_query = f"SELECT SUM(populacao_regiao_2025::FLOAT) FROM (SELECT DISTINCT regiao, populacao_regiao_2025 FROM gold_marketplace_odontogroup {where_str})"
        pop_row = db_conn.cursor().execute(pop_query, params).fetchone()
        true_total_pop = float(pop_row[0]) if pop_row and pop_row[0] else 0.0
        
        # Assume roughly half population for F and M for penetration (since we lack demographic specific pop)
        true_pop_f = true_total_pop
        true_pop_m = true_total_pop

        # Aggregate by faixa_etaria and sexo
        query = f"""
            SELECT 
                faixa_etaria, 
                sexo,
                SUM(total_vidas_ativas::FLOAT) as total_vidas
            FROM gold_marketplace_odontogroup
            {where_str}
            GROUP BY faixa_etaria, sexo
            ORDER BY faixa_etaria
        """
        raw_data = db_conn.cursor().execute(query, params).fetchall()
        
        # Comparativo ODONTOGROUP
        where_odonto, params_odonto = build_odontogroup_where_clause(uf, regiao, municipio, faixa_etaria, sexo)
        query_odonto = f"""
            SELECT 
                faixa_etaria, 
                sexo,
                SUM(total_vidas_ativas::FLOAT) as total_vidas
            FROM gold_marketplace_odontogroup
            {where_odonto}
            GROUP BY faixa_etaria, sexo
        """
        raw_odonto = db_conn.cursor().execute(query_odonto, params_odonto).fetchall()
        
        odonto_dict = {}
        for row in raw_odonto:
            faixa = row[0]
            sexo = row[1]
            vidas = float(row[2]) if row[2] else 0.0
            if faixa not in odonto_dict:
                odonto_dict[faixa] = {"F": 0.0, "M": 0.0}
            if sexo in ['F', 'M']:
                odonto_dict[faixa][sexo] += vidas

        # Transform into a structured JSON
        faixas = {}
        for row in raw_data:
            faixa = row[0]
            if not faixa: continue
            sexo = row[1]
            vidas = float(row[2]) if row[2] else 0.0
            
            if faixa not in faixas:
                faixas[faixa] = {
                    "faixa": faixa,
                    "F_vidas": 0.0,
                    "M_vidas": 0.0,
                    "F_cobertura": 0.0,
                    "M_cobertura": 0.0,
                    "Total_vidas": 0.0,
                    "Total_cobertura": 0.0,
                    "F_pop": true_pop_f,
                    "M_pop": true_pop_m,
                    "odontogroup_F_vidas": odonto_dict.get(faixa, {}).get("F", 0.0),
                    "odontogroup_M_vidas": odonto_dict.get(faixa, {}).get("M", 0.0),
                    "odontogroup_Total_vidas": odonto_dict.get(faixa, {}).get("F", 0.0) + odonto_dict.get(faixa, {}).get("M", 0.0)
                }
            
            if sexo == 'F':
                faixas[faixa]["F_vidas"] += vidas
            elif sexo == 'M':
                faixas[faixa]["M_vidas"] += vidas
        
        results = []
        for f_data in faixas.values():
            f_data["Total_vidas"] = f_data["F_vidas"] + f_data["M_vidas"]
            
            # Penetration calculation
            if true_pop_f > 0:
                f_data["F_cobertura"] = round((f_data["F_vidas"] / true_pop_f) * 100, 2)
            if true_pop_m > 0:
                f_data["M_cobertura"] = round((f_data["M_vidas"] / true_pop_m) * 100, 2)
            if true_total_pop > 0:
                f_data["Total_cobertura"] = round((f_data["Total_vidas"] / true_total_pop) * 100, 2)
            
            results.append(f_data)
            
        return {"data": results}

    except Exception as e:
        print(f"Erro em dashboard_faixa_etaria: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/dashboard/saldo-adesoes")
@lru_cache(maxsize=128)
def dashboard_saldo_adesoes(uf: str = Query(None), operadora: str = Query(None), regiao: str = Query(None), municipio: str = Query(None), faixa_etaria: str = Query(None), sexo: str = Query(None)):
    """
    Retorna o saldo de adesões x cancelamentos agrupado por operadora (limitado ao top 50 por vidas ativas).
    Se uma operadora for selecionada, inclui ela e a Odontogroup para comparação.
    """
    if operadora and operadora.lower() != "todos":
        where_clause, params = build_where_clause(uf, None, regiao, municipio, faixa_etaria, sexo)
        if where_clause:
            where_clause += " AND (UPPER(nome_operadora) = UPPER(?) OR UPPER(nome_operadora) LIKE '%ODONTOGROUP%')"
        else:
            where_clause = "WHERE (UPPER(nome_operadora) = UPPER(?) OR UPPER(nome_operadora) LIKE '%ODONTOGROUP%')"
        params.append(operadora)
    else:
        where_clause, params = build_where_clause(uf, operadora, regiao, municipio, faixa_etaria, sexo)

    query = f"""
        SELECT 
            nome_operadora,
            SUM(total_vidas_aderidas) AS novas_vidas,
            SUM(total_vidas_canceladas) AS canceladas,
            SUM(total_vidas_ativas) AS total_vidas
        FROM gold_marketplace_odontogroup
        {where_clause}
        GROUP BY nome_operadora
        ORDER BY total_vidas DESC
    """
    
    with db_conn.cursor() as cursor:
        rows = cursor.execute(query, params).fetchall()
        
    result = []
    for row in rows:
        nome_op = row[0] if row[0] is not None else "Desconhecido"
        novas_vidas = int(row[1]) if row[1] is not None else 0
        canceladas = int(row[2]) if row[2] is not None else 0
        total_vidas = int(row[3]) if row[3] is not None else 0
        saldo = novas_vidas - canceladas
        
        result.append({
            "nome_operadora": str(nome_op),
            "novas_vidas": novas_vidas,
            "canceladas": canceladas,
            "total_vidas": total_vidas,
            "saldo": saldo,
            "is_odontogroup": "ODONTOGROUP" in str(nome_op).upper()
        })

    return result
