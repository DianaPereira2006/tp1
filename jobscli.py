import typer
import requests
import json
import csv
import re
import sys
from bs4 import BeautifulSoup
import unicodedata
from collections import defaultdict

app = typer.Typer()

url = "https://api.itjobs.pt/job/list.json"
api_key = "230c63de930638ddf1a3181f452389e6"
user_agent = {"User-Agent": "Mozilla/5.0"}

# Função para criar ficheiro com todos os dados da API
@app.command()
def dump(limit: int = 500, filename: str = "empregos.json"):
    """
    Cria um ficheiro JSON com até N empregos da API
    """
    all_jobs = []
    offset = 0

    while len(all_jobs) < limit:
        params = {
            "api_key": api_key,
            "limit": min(200, limit - len(all_jobs)),  
            "offset": offset
        }

        response = requests.get(url, headers=user_agent, params=params)
        if response.status_code != 200:
            print("Erro:", response.status_code)
            break

        jobs = response.json().get("results", [])
        if not jobs:
            break

        all_jobs.extend(jobs)
        offset += 200

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"Ficheiro criado: {filename} ({len(all_jobs)} empregos guardados)")

# TP1 e) e TP2 d) Função para exportar dados para CSV
def export_csv(data, filename, mode="default"):
    """
    Exporta dados para CSV.
    mode = "default"   -> lista de jobs (TP1)
    mode = "teamlyzer" -> job único enriquecido (TP2 a + d)
    """

    with open(filename, "w", newline="", encoding="utf-8") as f:

        # CSV TP1
        if mode == "default":
            fieldnames = ["titulo", "empresa", "descrição", "data_publicação", "salário", "localização"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for job in data:
                writer.writerow({
                    "titulo": job.get("title", "N/A"),
                    "empresa": job.get("company", {}).get("name", "N/A"),
                    "descrição": job.get("body", "N/A"),
                    "data_publicação": job.get("publishedAt", "N/A"),
                    "salário": job.get("wage", "N/A"),
                    "localização": ", ".join(loc["name"] for loc in job.get("locations", []))
                })

        # CSV alinea a) TP2
        elif mode == "teamlyzer":
            fieldnames = [
                "id", "titulo", "empresa",
                "teamlyzer_rating",
                "teamlyzer_description",
                "teamlyzer_benefits",
                "teamlyzer_salary"
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            writer.writerow({
                "id": data.get("id"),
                "titulo": data.get("title"),
                "empresa": data.get("company", {}).get("name"),
                "teamlyzer_rating": data.get("teamlyzer_rating"),
                "teamlyzer_description": data.get("teamlyzer_description"),
                "teamlyzer_benefits": data.get("teamlyzer_benefits"),
                "teamlyzer_salary": data.get("teamlyzer_salary")
            })

        # CSV alinea c) TP2
        elif mode == "skills":
            fieldnames = ["trabalho", "skill", "ocorrencias"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            trabalho = data.get("profissao", "")
            for item in data.get("top_skills", []):
                writer.writerow({
                    "trabalho": trabalho,
                    "skill": item.get("skill", ""),
                    "ocorrencias": item.get("count", 0)
                })

#-----------------TP1--------------------

# a) Função para mostrar os N trabalhos mais recentes
@app.command()
def top(n: int, short: bool = False,
        csv_export: bool = typer.Option(False, help="Exportar CSV")):
    """
    Mostra os N trabalhos mais recentes
    """
    
    params = {"api_key": api_key, "limit": n}
    res = requests.get(url, params=params, headers=user_agent)

    if res.status_code != 200:
        print("Erro:", res.status_code); return

    jobs = res.json().get("results", [])

    if short:
        for job in jobs:
            print({
                "id": job["id"],
                "titulo": job["title"],
                "empresa": job["company"]["name"]
            })
    else:
        print(json.dumps(jobs, indent=2, ensure_ascii=False))

    if csv_export:
        export_csv(jobs, "tops.csv")
        print("CSV criado: tops.csv")


# b) Função para mostrar os trabalhos part-time por empresa e localidade existentes
@app.command()
def search(localidade: str, empresa: str, n: int,
           csv_export: bool = typer.Option(False, help="Exportar CSV")):
    """
    Mostra os trabalhos part-time por empresa e localidade
    """

    params = {"api_key": api_key, "limit": 200}
    response = requests.get(url, params=params, headers=user_agent)

    if response.status_code != 200:
        print("Erro:", response.status_code)
        return

    jobs = response.json().get("results", [])
    results = []

    empresa_low = empresa.lower()
    local_low = localidade.lower()

    for job in jobs:
        job_emp = job.get("company", {}).get("name", "").lower()
        job_locs = [loc["name"].lower() for loc in job.get("locations", [])]
        job_types = [t["name"].lower() for t in job.get("types", [])]
        body = job.get("body", "").lower()

        is_part_time = (
            any("part-time" in t for t in job_types) or
            any("part time" in t for t in job_types) or
            "part-time" in body or
            "part time" in body or
            "tempo parcial" in body or
            "horário reduzido" in body
        )

        if (empresa_low in job_emp and
            any(local_low in loc for loc in job_locs) and
            is_part_time):
            results.append(job)

        if len(results) >= n:
            break

    print(json.dumps(results, indent=2, ensure_ascii=False))

    if csv_export:
        filename = f"{empresa}_{localidade}.csv"
        export_csv(results, filename)
        print(f"CSV criado: {filename}")


# c) Função para mostrar qual o regime do trabalho (remoto/híbrido/presencial/outro)
@app.command()
def type(job_id: int):
    """
    Mostra o regime do trabalho
    """
    params = {"api_key": api_key, "id": job_id} 
    res = requests.get(url, params=params, headers=user_agent)

    if res.status_code != 200:
        emprego = res.json()
        descricao = emprego.get("body", "")

        hibrido = re.search(r"([Hh][íi]brido|[Hh]ybrid)", descricao)
        presencial = re.search(r"([Pp]resencial|[Oo]n-?site)", descricao)

        if emprego.get("allowRemote"):
            typer.echo("Remoto")
        elif hibrido:
            typer.echo("Híbrido")
        elif presencial:
            typer.echo("Presencial")
        else:
            typer.echo("Não identificado")
    else:
        print(f"Erro na requisição: {res.status_code} - {res.reason}")

# d) Função para contar ocorrências de skills entre duas datas
@app.command()
def skills(data_inicial: str, data_final: str):
    """
    Conta ocorrências de skills entre duas datas
    """

    params = {
        "api_key": api_key,
        "published_after": data_inicial,
        "published_before": data_final,
        "limit": 200
    }

    response = requests.get(url, headers=user_agent, params=params)

    if response.status_code == 200:
        jobs = response.json().get("results", [])
        text = " ".join(job.get("body", "") for job in jobs).lower()

        skill_list = ["python", "java", "javascript", "sql", "c#", "c++", "aws",
                      "docker", "react", "linux", "html", "css"]

        counts = {skill: len(re.findall(rf"\b{re.escape(skill)}\b", text)) for skill in skill_list}
        ordered = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        print(json.dumps(ordered, indent=2, ensure_ascii=False))
    else:
        print("Erro:", response.status_code)

#-----------------TP2--------------------

url_teamlyzer = "https://pt.teamlyzer.com/companies/"

# Função para ler HTML de uma URL
def ler_html(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TeamlyzerScraper/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return BeautifulSoup(resp.content, 'html.parser')
        else:
            return None
    except Exception as e:
        typer.echo(f"Erro de conexão: {e}")
        return None

# Função auxiliar para ajustar o slug
def ajustar_slug(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[-\s]+', '-', texto).lower().strip('-')

# Função para gerar o slug para a url do Teamlyzer a partir do nome da empresa
def encontrar_empresa(nome_empresa):
    tentativas = [
        ajustar_slug(nome_empresa),
        ajustar_slug(nome_empresa.split()[0]) if nome_empresa.split() else None
    ]

    for slug in filter(None, tentativas):
        url = f"{url_teamlyzer}{slug}"
        soup = ler_html(url)
        if soup and soup.title and "404" not in soup.title.text.lower():
            return slug

    return None

# Função auxiliar para extrair benefícios
def extrair_beneficios(soup):
    beneficios = []

    for li in soup.select("li.flex_group .flex_details"):
        texto = li.get_text(strip=True)
        if texto:
            beneficios.append(texto)

    return list(dict.fromkeys(beneficios))  # remove duplicados
    
# Função para obter informações do Teamlyzer
def info(res):
    if not res:
        return {}
    
    # Obtém o nome da empresa
    nome_empresa = res.get("company", {}).get("name", "")
    if not nome_empresa:
        return {}
    
    # Procura o slug da empresa
    slug_alterado = encontrar_empresa(nome_empresa)
    if slug_alterado:
        empresa_teamlyzer = slug_alterado
    else:
        # Slug normal
        empresa_teamlyzer = nome_empresa.replace(" ", "-").lower()
    
    # Constrói a URL da empresa no Teamlyzer
    url_pesquisa = url_teamlyzer + empresa_teamlyzer
    soup = ler_html(url_pesquisa)
    
    # Se não encontrar a empresa
    if not soup:
        typer.echo(f"Erro ao acessar Teamlyzer para {nome_empresa}", err=True)
        return {"Não foi possível obter informações do Teamlyzer para esta empresa."}
    
    resultados = {}
    
    # Rating
    rating_container = soup.find("span", class_=re.compile(r'[a-z]+_rating'))  
    if rating_container:
        texto = rating_container.get_text(strip=True)
        # Separa a parte antes da barra, se existir
        if '/' in texto:
            texto_rating = texto.split('/')[0].strip()
        else:
            texto_rating = texto
        # Tenta converter diretamente para float
        try:
            resultados["teamlyzer_rating"] = float(texto_rating)
        except ValueError:
                # Tenta extrair número decimal com expressão regular
                decimal = re.search(r"(\d+\.\d+)", texto) 
                if decimal:
                    resultados["teamlyzer_rating"] = float(decimal.group(1))
                else:
                    resultados["teamlyzer_rating"] = 0.0
    else:
        resultados["teamlyzer_rating"] = 0.0
    
    # Descrição
    descricao = soup.find("div", class_="ellipsis center_mobile")
    # Limpar a descrição
    if descricao:
        # Remover elementos indesejados
        for unwanted in descricao.find_all(class_=["read-more", "read-less", "more-link", "less-link"]): 
            unwanted.decompose()  
        texto_descricao = descricao.get_text(separator=" ", strip=True) 
        texto_descricao = texto_descricao.replace("…", "") 
        resultados["teamlyzer_description"] = texto_descricao[:1000]
    else:
        resultados["teamlyzer_description"] = "Descrição não encontrada"
    
    # Benefícios
    beneficios = extrair_beneficios(soup)

    if not beneficios:
        soup_beneficios = ler_html(url_pesquisa + "/benefits-and-values")
        if soup_beneficios:
            beneficios = extrair_beneficios(soup_beneficios)

    resultados["teamlyzer_benefits"] = "; ".join(beneficios) if beneficios else "Nenhuma informação"

    # Salario medio
    for panel in soup.select("div.panel.mini-box"):
        if panel.select_one("i.fa-eur"):
            texto = panel.select_one("p.size-h2")
            if texto:
                valores = re.findall(r'[\d\.,]+€', texto.get_text())
                if valores:
                    resultados["teamlyzer_salary"] = " - ".join(valores)
                    break
    else:
        resultados["teamlyzer_salary"] = "Nenhuma informação"
    
    return resultados

# a) Função para obter informação do Teamlyzer de um job pelo seu ID
@app.command()
def get(job_id: int = typer.Argument(..., help="ID do trabalho"),csv_export: bool = typer.Option(False, "--csv-export", help="Exportar para CSV")):
    # Obter dados do job da API ITJobs
    url_itjobs = "https://api.itjobs.pt/job/get.json"
    params = {"api_key": "5ead20f487935ddbab9b3f084acdbf63", "id": job_id}
    try:
        res_itjobs = requests.get(url_itjobs, headers=user_agent, params=params, timeout=10)
        res_itjobs.raise_for_status()
        dados_job = res_itjobs.json()
    except Exception as e:
        typer.echo(f"Erro ao obter dados do job {job_id}: {e}")
        raise typer.Exit(code=1)
    # Dados do Teamlyzer
    teamlyzer_info = info(dados_job)
    final = {
        "id": dados_job.get("id", ""),
        "teamlyzer_rating": teamlyzer_info.get("teamlyzer_rating", 0.0),
        "teamlyzer_description": teamlyzer_info.get("teamlyzer_description", ""),
        "teamlyzer_benefits": teamlyzer_info.get("teamlyzer_benefits", ""),
        "teamlyzer_salary": teamlyzer_info.get("teamlyzer_salary", "")
    }
    # Output
    print(json.dumps(final, indent=4, ensure_ascii=False))
    
    # Exportação CSV opcional
    if csv_export:
        export_csv(final, f"job_{job_id}.csv", mode="teamlyzer")
        print(f"CSV criado: job_{job_id}.csv")


# b) Função para criar estatísticas de vagas por zona e tipo de trabalho
@app.command()
def statistics(limit: int = 500,):
    """
    Cria estatísticas de vagas por zona e tipo de trabalho
    """

    todos_jobs = []
    offset = 0

    # Procurar até atingir o limite
    while len(todos_jobs) < limit:
        params = {
            "api_key": api_key,
            "limit": min(200, limit - len(todos_jobs)),
            "offset": offset
        }
        response = requests.get(url, headers=user_agent, params=params)

        # Verificar resposta
        if response.status_code != 200:
            typer.echo("Erro ao aceder à API")
            return
        jobs = response.json().get("results", [])
        if not jobs:
            break
        todos_jobs.extend(jobs)
        offset += 200
    # Contar vagas por zona e tipo
    counter = defaultdict(int)

    # Analisar cada trabalho
    for job in todos_jobs:
        # Zona
        locations = job.get("locations", [])
        zonas = [loc.get("name", "Desconhecida") for loc in locations] or ["Desconhecida"]

        # Posição
        posicao = job.get("title", "Desconhecida")


        for zona in zonas:
            counter[(zona, posicao)] += 1

    # Converter para lista de dicionários
    resultados = [
        {
        "zona": zona,
        "posicao": posicao,
        "numero_vagas": count
        }
        for (zona, tipo), count in counter.items()
    ]

    # Output terminal
    print(json.dumps(resultados, indent=2, ensure_ascii=False))

# c) Função para listar as top 10 skills para um determinado trabalho no Teamlyzer 
@app.command(name="list")
def list_data(
    data_type: str = typer.Argument(..., help="Tipo de dado a listar (skills)"),
    search_term: str = typer.Argument(..., help="Cargo/trabalho (ex: 'data scientist')"),
    csv_export: bool = typer.Option(False, "--csv-export", help="Exportar para CSV")
):
    """
    Lista as top 10 skills associadas a um determinado trabalho no Teamlyzer
    """

    if data_type.lower() != "skills":
        typer.echo("Apenas o tipo 'skills' é suportado.", err=True)
        raise typer.Exit(code=1)

    # Construir URL de Teamlyzer para a profissão
    slug = search_term.strip().replace(" ", "_")  # encode spaces
    filename = f"skills_{slug}.csv"
    url_skills = f"https://pt.teamlyzer.com/companies/jobs?profession_role={slug}&order=most_relevant"

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url_skills, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        typer.echo(f"Erro ao aceder ao Teamlyzer: {e}", err=True)
        raise typer.Exit(code=1)

    soup = BeautifulSoup(response.text, "html.parser")

    # Contar skills
    contagem = {}
    skills_divs = soup.find_all("div", {"class": "voffset2"})
    for div in skills_divs:
        skill_elem = div.find("a")
        if skill_elem and skill_elem.text:
            skill = skill_elem.text.strip()
            contagem[skill] = contagem.get(skill, 0) + 1

    if not contagem:
        typer.echo("Nenhuma skill encontrada para essa profissão.", err=True)
        raise typer.Exit(code=1)

    contagem_ordenada = sorted(contagem.items(), key=lambda item: item[1], reverse=True)

    top_skills = [{"skill": skill, "count": count} for skill, count in contagem_ordenada[:10]]

    resultado = {
        "profissao": search_term,
        "top_skills": top_skills
    }

    # Mostrar resultado no terminal
    typer.echo(json.dumps(resultado, indent=4, ensure_ascii=False))

    # Criar CSV 
    if csv_export:
        filename = f"skills_{slug}.csv"
        export_csv(resultado, filename, mode="skills")
        print(f"CSV criado: {filename}")


def como_usar():
    print("""
    ============================
    Como utilizar:
    ----------------------------
    python jobscli.py dump --limit N                               -> Exporta empregos da API para ficheiro JSON
    python jobscli.py top N [--short] [--csv-export]               -> Mostra N empregos mais recentes
    python jobscli.py search LOCAL "EMPRESA" N [--csv-export]      -> Procura part-time por empresa/localidade
    python jobscli.py type JOB_ID                                  -> Mostra regime (remoto/híbrido/presencial/outro)
    python jobscli.py skills DATA_INICIAL DATA_FINAL               -> Conta skills entre duas datas
    python jobscli.py get JOB_ID [--csv-export]                    -> Obtém informacao do Teamlyzer de um emprego
    python jobscli.py statistics                                   -> Cria estatísticas de vagas por zona e tipo
    python jobscli.py list skills "TRABALHO" [--csv-export]        -> Lista top 10 skills para um trabalho
    ============================
    """)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        como_usar()
    else:
        app()