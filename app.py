# =========================
# 1) IMPORTAÇÕES
# =========================
import streamlit as st
import json
import os
from datetime import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
import urllib.parse
import hashlib
import re
import base64
from pathlib import Path
import sys
import pandas as pd
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
import unicodedata


# =========================
# 2) CONFIGURAÇÕES GERAIS
# =========================
APP_TITLE = "RA - Gestão de Acordos"
APP_ICON = "🤖"

WHATSAPP_BUSINESS_NUMBER = "553130253464"
WHATSAPP_BUSINESS_NUMBER_DISPLAY = "+55 31 3025-3464"

LEAD_RETURN_NUMBER = "5531993350669"
LEAD_RETURN_NUMBER_DISPLAY = "+55 31 99335-0669"

FASE_0 = 'Cadastrado'
FASE_1 = 'MSG inicial enviada'
FASE_2 = 'MSG Contra enviada'
FASE_3 = 'Lead enviada'
FASE_4 = 'Minuta Enviada'
FASE_5 = 'Recusados'
FASE_6 = 'Concluído'

FASE_0_COR = '⚪'
FASE_1_COR = '🟡'
FASE_2_COR = '🟠'
FASE_3_COR = '🟢'
FASE_4_COR = '🟣'
FASE_5_COR = '⚫'
FASE_6_COR = '🔵'

FASES_INFO = {
    0: {"icone": FASE_0_COR, "nome": FASE_0, "cor": "phase-0", "descricao": "Caso cadastrado, aguardando envio de mensagem"},
    1: {"icone": FASE_1_COR, "nome": FASE_1, "cor": "phase-1", "descricao": "Mensagem enviada, aguardando resposta do cliente"},
    2: {"icone": FASE_2_COR, "nome": FASE_2, "cor": "phase-2-nao", "descricao": "Resposta negativa. Questionado se há contra porposta"},
    3: {"icone": FASE_3_COR, "nome": FASE_3, "cor": "phase-3", "descricao": "Resposta positiva, enviada a lead"},
    4: {"icone": FASE_4_COR, "nome": FASE_4, "cor": "phase-4", "descricao": "Minuta enviada, aguardando retorno final"},
    5: {"icone": FASE_5_COR, "nome": FASE_5, "cor": "phase-2-nao", "descricao": "Caso recusado"},
    6: {"icone": FASE_6_COR, "nome": FASE_6, "cor": "phase-2-sim", "descricao": "Caso concluído"},
}

# =========================
# 2.1) RÓTULOS DOS CAMPOS
# =========================
LABEL_NOME_CASO = "Nome da Parte"
LABEL_IDENTIFICADOR = "GCPJ"
LABEL_PROCESSO = "Número do Processo"
LABEL_ALCADA = "Alçada Máxima"
LABEL_VARA = "Vara"
LABEL_ORGAO = "Órgão Julgador"
LABEL_COMARCA = "Comarca"


# =========================
# 3) DIRETÓRIOS E ARQUIVOS
# =========================
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

ARQ_CASOS_BRADESCO = APP_DIR / "casos_bradesco.json"
ARQ_CONTATOS = APP_DIR / "contatos.json"

ARQ_COMARCAS_MG = APP_DIR / "comarcas_mg.json"

LOGO_BRADESCO = APP_DIR / "logobradesco.png"
LOGO_RA = APP_DIR / "ralogo.png"

EDGE_DEBUG_HOST = "127.0.0.1:9222"
EDGE_PROFILE_DIR = APP_DIR / "edge_profile"


# =========================
# 4) FUNÇÕES DE ARQUIVO
# =========================
def carregar_json(caminho, valor_padrao):
    caminho = Path(caminho)

    if not caminho.exists():
        salvar_json(caminho, valor_padrao)
        return valor_padrao

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return valor_padrao


def salvar_json(caminho, dados):
    caminho = Path(caminho)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def carregar_comarcas_mg():
    return carregar_json(ARQ_COMARCAS_MG, [])

def image_to_base64(image_path):
    """Converte imagem para base64."""
    try:
        image_path = Path(image_path)
        if image_path.exists():
            with open(image_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode()
        return None
    except Exception as e:
        st.error(f"Erro ao carregar imagem {image_path}: {e}")
        return None

def executar_rotina_automatica(bot, banco):
    """Executa envio dos pendentes e depois verifica retornos."""
    logs = []

    try:
        sucesso_envio, msg_envio = bot.enviar_mensagem_caso(banco)
        logs.append(f"Envio: {msg_envio}")

        sucesso_retorno, msg_retorno = bot.verificar_retornos(banco)
        logs.append(f"Retornos: {msg_retorno}")

        return True, logs

    except Exception as e:
        return False, [f"Erro na rotina automática: {e}"]

# =========================
# 5) CLASSE BASE DO BOT
# =========================
class WhatsAppBotAPI:
    def __init__(self):
        # Diretório único do app
        self.app_dir = APP_DIR

        # Arquivos locais do app
        self.arquivo_contatos = ARQ_CONTATOS
        self.arquivo_casos_bradesco = ARQ_CASOS_BRADESCO

        # Identidade do canal
        self.whatsapp_business_number = WHATSAPP_BUSINESS_NUMBER
        self.whatsapp_business_number_display = WHATSAPP_BUSINESS_NUMBER_DISPLAY
        self.lead_return_number = LEAD_RETURN_NUMBER
        self.lead_return_number_display = LEAD_RETURN_NUMBER_DISPLAY

        # Drivers Selenium
        self.driver = None
        self.wait = None

    # =========================
    # 5.1) GERENCIAMENTO DE ARQUIVOS
    # =========================
    def carregar_contatos(self):
        """Carrega base de contatos."""
        try:
            return carregar_json(self.arquivo_contatos, {})
        except Exception as e:
            st.error(f"Erro ao carregar contatos: {e}")
            return {}

    def salvar_contatos(self, dados):
        """Salva base de contatos."""
        try:
            salvar_json(self.arquivo_contatos, dados)
            return True
        except Exception as e:
            st.error(f"Erro ao salvar contatos: {e}")
            return False

    def carregar_casos(self):
        """Carrega base de casos do Bradesco."""
        try:
            return {
                "BRADESCO": carregar_json(self.arquivo_casos_bradesco, {})
            }
        except Exception as e:
            st.error(f"Erro ao carregar casos: {e}")
            return {"BRADESCO": {}}

    def salvar_casos(self, banco, dados):
        """Salva casos do Bradesco."""
        try:
            salvar_json(self.arquivo_casos_bradesco, dados)
            return True
        except Exception as e:
            st.error(f"Erro ao salvar casos do {banco}: {e}")
            return False

    # =========================
    # 5.2) VALIDAÇÕES
    # =========================
    def validar_telefone(self, telefone):
        """Valida formato do telefone: 55XX9XXXXXXXX."""
        if not telefone:
            return False, "Telefone não pode estar vazio"

        telefone_limpo = re.sub(r"\D", "", telefone)

        if len(telefone_limpo) != 13:
            return False, "Telefone deve ter 13 dígitos no formato 55XX9XXXXXXXX"

        if not telefone_limpo.startswith("55"):
            return False, "Telefone deve começar com 55"

        return True, telefone_limpo

    def validar_cpf(self, cpf):
        """Valida formato do CPF: 11 dígitos."""
        if not cpf:
            return False, "CPF não pode estar vazio"

        cpf_limpo = re.sub(r"\D", "", cpf)

        if len(cpf_limpo) != 11:
            return False, "CPF deve ter exatamente 11 dígitos"

        return True, cpf_limpo

    def validar_oab(self, oab):
        """Valida formato mínimo da OAB."""
        if not oab:
            return False, "OAB não pode estar vazia"

        if len(oab.strip()) < 3:
            return False, "OAB deve ter pelo menos 3 caracteres"

        return True, oab.strip()

    # =========================
    # 5.3) CONTATOS
    # =========================
    def adicionar_contato(self, nome, telefone, celular, email, oab=None, cpf=None, uf_oab="MG"):
        """Adiciona novo contato à base."""
        try:
            contatos = self.carregar_contatos()

            telefone_valido, telefone_msg = self.validar_telefone(telefone)
            if not telefone_valido:
                return False, telefone_msg

            telefone_limpo = telefone_msg

            celular_limpo = ""
            if celular and str(celular).strip():
                celular_valido, celular_msg = self.validar_telefone(celular)
                if not celular_valido:
                    return False, f"Celular: {celular_msg}"
                celular_limpo = celular_msg

            oab_limpa = oab.strip() if oab and oab.strip() else None
            cpf_limpo = cpf.strip() if cpf and cpf.strip() else None
            uf_oab_final = str(uf_oab or "MG").strip().upper()

            if not oab_limpa and not cpf_limpo:
                return False, "É necessário informar OAB ou CPF"

            oab_final = None
            if oab_limpa:
                oab_valido, oab_msg = self.validar_oab(oab_limpa)
                if not oab_valido:
                    return False, oab_msg
                oab_final = oab_msg

            cpf_final = None
            if cpf_limpo:
                cpf_valido, cpf_msg = self.validar_cpf(cpf_limpo)
                if not cpf_valido:
                    return False, cpf_msg
                cpf_final = cpf_msg

            for _, dados_existentes in contatos.items():
                if dados_existentes.get("telefone") == telefone_limpo:
                    return False, f"Telefone já cadastrado para {dados_existentes['nome']}"

                if oab_final and dados_existentes.get("oab") == oab_final:
                    return False, f"OAB {oab_final} já está cadastrada"

                if cpf_final and dados_existentes.get("cpf") == cpf_final:
                    return False, f"CPF {cpf_final} já está cadastrado"

            if oab_final:
                id_contato = f"contato_oab_{oab_final}"
            elif cpf_final:
                id_contato = f"contato_cpf_{cpf_final}"
            else:
                hash_id = hashlib.md5(f"{telefone_limpo}_{time.time()}".encode()).hexdigest()[:10]
                id_contato = f"contato_{hash_id}"

            nome_limpo = nome.strip() if nome else ""
            email_final = email.strip() if email else ""
            tipo = "Advogado" if oab_final else "Cliente"

            novo_contato = {
                "nome": nome_limpo,
                "telefone": telefone_limpo,
                "celular": celular_limpo,
                "email": email_final,
                "oab": oab_final,
                "cpf": cpf_final,
                "tipo": tipo,
                "data_cadastro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "uf_oab": uf_oab_final if oab_final else "",
            }

            contatos[id_contato] = novo_contato

            if self.salvar_contatos(contatos):
                return True, f"✅ Contato '{nome_limpo}' cadastrado com sucesso!"
            return False, "❌ Erro ao salvar dados no arquivo"

        except Exception as e:
            return False, f"❌ Erro inesperado: {str(e)}"

    def editar_contato(self, contato_id_antigo, novo_nome, novo_telefone, novo_celular, novo_email, nova_oab=None, novo_cpf=None, nova_uf_oab="MG"):
        """Edita dados de contato existente."""
        contatos = self.carregar_contatos()

        if contato_id_antigo not in contatos:
            return False, "Contato não encontrado"

        telefone_valido, telefone_msg = self.validar_telefone(novo_telefone)
        if not telefone_valido:
            return False, telefone_msg

        novo_telefone_limpo = telefone_msg

        novo_celular_limpo = ""
        if novo_celular and str(novo_celular).strip():
            celular_valido, celular_msg = self.validar_telefone(novo_celular)
            if not celular_valido:
                return False, f"Celular: {celular_msg}"
            novo_celular_limpo = celular_msg

        nova_oab_limpo = None
        novo_cpf_limpo = None
        nova_uf_oab_final = str(nova_uf_oab or "MG").strip().upper()

        if not (nova_oab and nova_oab.strip()) and not (novo_cpf and novo_cpf.strip()):
            return False, "É necessário informar OAB ou CPF"

        if nova_oab and nova_oab.strip():
            oab_valido, oab_msg = self.validar_oab(nova_oab)
            if not oab_valido:
                return False, oab_msg
            nova_oab_limpo = oab_msg

            for contato_id, dados in contatos.items():
                if contato_id != contato_id_antigo and dados.get("oab") == nova_oab_limpo:
                    return False, f"OAB {nova_oab_limpo} já está cadastrada para outro contato"

        if novo_cpf and novo_cpf.strip():
            cpf_valido, cpf_msg = self.validar_cpf(novo_cpf)
            if not cpf_valido:
                return False, cpf_msg
            novo_cpf_limpo = cpf_msg

            for contato_id, dados in contatos.items():
                if contato_id != contato_id_antigo and dados.get("cpf") == novo_cpf_limpo:
                    return False, f"CPF {novo_cpf_limpo} já está cadastrado para outro contato"

        for contato_id, dados in contatos.items():
            if contato_id != contato_id_antigo and dados["telefone"] == novo_telefone_limpo:
                return False, f"Telefone já cadastrado para {dados['nome']}"

        contato_antigo = contatos[contato_id_antigo]

        if nova_oab_limpo and contato_antigo.get("oab") != nova_oab_limpo:
            novo_contato_id = f"contato_oab_{nova_oab_limpo}"
            dados_contato = contatos.pop(contato_id_antigo)
        elif novo_cpf_limpo and contato_antigo.get("cpf") != novo_cpf_limpo:
            novo_contato_id = f"contato_cpf_{novo_cpf_limpo}"
            dados_contato = contatos.pop(contato_id_antigo)
        else:
            novo_contato_id = contato_id_antigo
            dados_contato = contatos[contato_id_antigo]

        dados_contato.update({
            "nome": novo_nome.strip(),
            "telefone": novo_telefone_limpo,
            "celular": novo_celular_limpo,
            "email": novo_email.strip() if novo_email else "",
            "oab": nova_oab_limpo,
            "cpf": novo_cpf_limpo,
            "tipo": "Advogado" if nova_oab_limpo else "Cliente",
            "uf_oab": nova_uf_oab_final if nova_oab_limpo else "",
        })

        contatos[novo_contato_id] = dados_contato

        if self.salvar_contatos(contatos):
            return True, "Contato atualizado com sucesso"
        return False, "Erro ao salvar dados"

    # =========================
    # 5.4) CASOS
    # =========================
    def adicionar_caso(
        self,
        banco,
        nome_caso,
        identificador,
        processo,
        contato_id,
        alcada_maxima="",
        numero_orgao=None,
        tipo_orgao="",
        comarca=""
    ):
        """Adiciona novo caso à base."""
        contatos = self.carregar_contatos()

        if contato_id not in contatos:
            return False, "Contato não encontrado"

        contato = contatos[contato_id]
        caso_id = f"caso_{contato['telefone']}_{int(time.time())}"

        casos = self.carregar_casos()

        if banco not in casos:
            casos[banco] = {}

        casos[banco][caso_id] = {
            "contato_id": contato_id,
            "nome_caso": nome_caso,
            "nome": contato["nome"],
            "telefone": contato["telefone"],
            "email": contato.get("email", ""),
            "oab": contato.get("oab"),
            "cpf": contato.get("cpf"),
            "tipo": contato["tipo"],
            "processo": processo,
            "numero_orgao": numero_orgao,
            "tipo_orgao": tipo_orgao,
            "comarca": comarca,
            "identificador": identificador,
            "alcada_maxima": alcada_maxima,
            "fase": 0,
            "data_cadastro": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "data_envio": None,
            "data_envio_contra": None,
            "data_resposta": None,
            "data_lead": None,
            "lead_enviada": False,
            "resposta": None,
            "resposta_texto": None,
            "valor_proposta_inicial": None,
            "contra_proposta_valor": None,
            "contra_proposta_texto": None,
            "aguardando_resposta_90": False,
            "ultimo_texto_lido_fase_2": None,
            "valor_limite_final": None,
            "minuta_enviada": False,
            "negociador": None,
        }

        if self.salvar_casos(banco, casos[banco]):
            return True, "Caso adicionado com sucesso (FASE 0)"
        return False, "Erro ao salvar caso"

    def atualizar_fase_caso(self, banco, caso_id, nova_fase, resposta=None, negociador=None):
        """Atualiza fase do caso."""
        casos = self.carregar_casos()

        if banco in casos and caso_id in casos[banco]:
            caso = casos[banco][caso_id]
            caso["fase"] = nova_fase

            if nova_fase == 0:
                caso["data_envio"] = None
                caso["data_envio_contra"] = None
                caso["data_resposta"] = None
                caso["data_lead"] = None
                caso["lead_enviada"] = False
                caso["resposta"] = None
                caso["resposta_texto"] = None
                caso["valor_proposta_inicial"] = None
                caso["contra_proposta_valor"] = None
                caso["aguardando_resposta_90"] = False
                caso["ultimo_texto_lido_fase_2"] = None
                caso["contra_proposta_texto"] = None

            elif nova_fase == 1:
                caso["data_envio"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                caso["data_envio_contra"] = None
                caso["data_resposta"] = None
                caso["data_lead"] = None
                caso["lead_enviada"] = False
                caso["resposta"] = None
                caso["resposta_texto"] = None
                caso["contra_proposta_valor"] = None
                caso["contra_proposta_texto"] = None
                caso["aguardando_resposta_90"] = False
                caso["ultimo_texto_lido_fase_2"] = None

            elif nova_fase == 2:
                caso["data_envio_contra"] = datetime.now().strftime("%d/%m/%Y %H:%M")

            elif nova_fase == 3:
                caso["data_lead"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                caso["lead_enviada"] = True
                caso["aguardando_resposta_90"] = False
                caso["ultimo_texto_lido_fase_2"] = None

            elif nova_fase == 4:
                caso["minuta_enviada"] = True

            elif nova_fase == 5:
                caso["data_resposta"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                caso["aguardando_resposta_90"] = False
                caso["ultimo_texto_lido_fase_2"] = None

            if resposta is not None:
                caso["resposta"] = resposta
                caso["data_resposta"] = datetime.now().strftime("%d/%m/%Y %H:%M")

            if nova_fase == 3 and negociador:
                caso["negociador"] = negociador

            if self.salvar_casos(banco, casos[banco]):
                return True, f"Fase atualizada para {nova_fase}"

        return False, "Caso não encontrado"

    def editar_caso(self, banco, caso_id, **kwargs):
        """Edita dados de um caso existente."""
        casos = self.carregar_casos()
        contatos = self.carregar_contatos()

        if banco in casos and caso_id in casos[banco]:
            caso = casos[banco][caso_id]

            novo_contato_id = kwargs.get("contato_id")
            if novo_contato_id and novo_contato_id in contatos:
                contato = contatos[novo_contato_id]
                kwargs["nome"] = contato["nome"]
                kwargs["telefone"] = contato["telefone"]
                kwargs["email"] = contato.get("email", "")
                kwargs["oab"] = contato.get("oab")
                kwargs["cpf"] = contato.get("cpf")
                kwargs["tipo"] = contato["tipo"]

            caso.update(kwargs)

            if self.salvar_casos(banco, casos[banco]):
                return True, "Caso atualizado com sucesso"

        return False, "Caso não encontrado"
    
    def apagar_caso(self, banco, caso_id):
        """Apaga um caso existente."""
        casos = self.carregar_casos()

        if banco in casos and caso_id in casos[banco]:
            del casos[banco][caso_id]
            if self.salvar_casos(banco, casos[banco]):
                return True, "Caso apagado com sucesso"

        return False, "Caso não encontrado"
    
    def obter_telefone_destinatario(self, caso):
        """Obtém o telefone atual do contato vinculado ao caso."""
        contatos = self.carregar_contatos()
        contato_id = caso.get("contato_id")

        if not contato_id or contato_id not in contatos:
            return None, None

        contato = contatos[contato_id]
        telefone = re.sub(r"\D", "", str(contato.get("telefone", "")).strip())
        nome = str(contato.get("nome", "")).strip()

        if len(telefone) != 13:
            return None, None

        return telefone, nome
    def normalizar_texto(self, texto):
        if not texto:
            return ""

        texto = str(texto).strip().lower()
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
        texto = re.sub(r"[^\w\s,.]", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto

    def converter_valor_brl_para_float(self, valor):
        """Converte texto BRL para float. Ex.: '5.000,00' -> 5000.00"""
        if valor is None:
            return 0.0

        texto = str(valor).strip()
        if not texto:
            return 0.0

        texto = texto.replace("R$", "").replace("r$", "").replace(" ", "")
        texto = texto.replace(".", "").replace(",", ".")

        try:
            return float(texto)
        except Exception:
            return 0.0

    def formatar_valor_brl(self, valor):
        """Formata float para BRL. Ex.: 2500 -> R$ 2.500,00"""
        try:
            valor_float = float(valor or 0)
        except Exception:
            valor_float = 0.0

        texto = f"{valor_float:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    def calcular_proposta_inicial(self, caso):
        alcada = self.converter_valor_brl_para_float(caso.get("alcada_maxima", "0"))
        return round(alcada * 0.5, 2)
    
    def calcular_limite_final(self, caso):
        alcada = self.converter_valor_brl_para_float(caso.get("alcada_maxima", "0"))
        return round(alcada * 0.9, 2)  

    def classificar_resposta_inicial(self, texto):
        """
        Retorna:
        - 'POSITIVO'
        - 'NEGATIVO'
        - None
        """
        t = self.normalizar_texto(texto)

        if not t:
            return None

        for termo in self.obter_gatilhos_positivos():
            if termo in t:
                return "POSITIVO"

        for termo in self.obter_gatilhos_negativos():
            if termo in t:
                return "NEGATIVO"

        return None

    def classificar_resposta_contra(self, texto):
        """
        Para a fase 2:
        - se identificar valor -> retorna float
        - se identificar resposta positiva -> 'POSITIVO'
        - se identificar negativa final -> 'NEGATIVO'
        - senão -> None
        """
        if not texto:
            return None

        valor = self.extrair_valor_monetario(texto)
        if valor is not None:
            return valor

        t = self.normalizar_texto(texto)
        if not t:
            return None

        for termo in self.obter_gatilhos_positivos():
            if termo in t:
                return "POSITIVO"

        negativos_contra = self.obter_gatilhos_negativos() + self.obter_gatilhos_negativos_contra_extra()

        for termo in negativos_contra:
            if termo == t or termo in t:
                return "NEGATIVO"

        return None

    def extrair_valor_monetario(self, texto):
        """
        Extrai valor monetário de textos como:
        - 7500
        - 7.500
        - 7.500,00
        - R$ 7.500,00
        - 3000,00
        - 7500 eu aceito
        """
        if not texto:
            return None

        texto = str(texto)

        padrao = r'R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?|(?<!\d)\d{1,3}(?:\.\d{3})+(?:,\d{2})?(?!\d)|(?<!\d)\d+(?:,\d{2})?(?!\d)'
        encontrados = re.findall(padrao, texto, flags=re.IGNORECASE)

        if not encontrados:
            return None

        candidatos = []

        for item in encontrados:
            bruto = item.replace("R$", "").replace("r$", "").strip()

            if "." in bruto and "," in bruto:
                normalizado = bruto.replace(".", "").replace(",", ".")
            elif "," in bruto:
                normalizado = bruto.replace(",", ".")
            elif "." in bruto:
                partes = bruto.split(".")
                if len(partes[-1]) == 3 and all(p.isdigit() for p in partes):
                    normalizado = "".join(partes)
                else:
                    normalizado = bruto
            else:
                normalizado = bruto

            try:
                valor = float(normalizado)
                if valor > 0:
                    candidatos.append(valor)
            except Exception:
                continue

        if not candidatos:
            return None

        return max(candidatos)

    def enviar_lead(self, caso, telefone_destinatario, nome_destinatario, valor_referencia, origem="proposta inicial"):
        msg_lead = f"""LEAD - CONTATO COM SUCESSO

Nome do Caso: {caso.get('nome_caso', 'N/A')}
Contato: {nome_destinatario}
Telefone: {telefone_destinatario}
E-mail: {caso.get('email', 'N/A')}
GCPJ: {caso.get('identificador', 'N/A')}
Processo: {caso.get('processo', 'N/A')}
Origem: {origem}
Valor: {self.formatar_valor_brl(valor_referencia)}"""

        return self.enviar_mensagem_para_numero(self.lead_return_number, msg_lead)

    # =========================
    # 5.5) ESTATÍSTICAS
    # =========================
    def obter_estatisticas(self):
        """Obtém estatísticas dos casos por fase."""
        casos = self.carregar_casos()
        estatisticas = {
            "BRADESCO": {
                "total": 0,
                "fase_0": 0,
                "fase_1": 0,
                "fase_2": 0,
                "fase_3": 0,
                "fase_4": 0,
                "fase_5": 0,
                "fase_6": 0,
            },
        }

        for banco, casos_banco in casos.items():
            if banco in estatisticas:
                estatisticas[banco]["total"] = len(casos_banco)

                for _, caso in casos_banco.items():
                    fase = caso.get("fase", 0)

                    if fase == 0:
                        estatisticas[banco]["fase_0"] += 1
                    elif fase == 1:
                        estatisticas[banco]["fase_1"] += 1
                    elif fase == 2:
                        estatisticas[banco]["fase_2"] += 1
                    elif fase == 3:
                        estatisticas[banco]["fase_3"] += 1
                    elif fase == 4:
                        estatisticas[banco]["fase_4"] += 1
                    elif fase == 5:
                        estatisticas[banco]["fase_5"] += 1
                    elif fase == 6:
                        estatisticas[banco]["fase_6"] += 1

        return estatisticas


# =========================
# 6) BOT WHATSAPP / SELENIUM
# =========================
class WhatsAppBotCorrigido(WhatsAppBotAPI):
    def __init__(self):
        super().__init__()

    def consolidar_respostas_mensagens(self, mensagens):
        """Junta as mensagens recebidas após a última mensagem enviada pelo bot."""
        if not mensagens:
            return ""
        return " | ".join(m.strip() for m in mensagens if str(m).strip())

    def obter_gatilhos_positivos(self):
        return [
            "sim",
            "tenho interesse",
            "ha interesse",
            "me interessa",
            "possuo interesse",
            "tenho",
            "ha sim",
            "podemos",
            "quero",
            "aceito",
            "vamos",
            "tenho sim"
            "interesse sim",
            "tenho interesse sim",
            "sim tenho interesse",
            "ha interesse sim",
        ]

    def obter_gatilhos_negativos(self):
        return [
            "nao",
            "nao ha interesse",
            "nao tenho interesse",
            "nao ha",
            "sem interesse",
            "nao quero",
            "nao consigo",
            "nao podemos",
            "nao tenho",
            "sem possibilidade",
            "sem acordo",
        ]

    def obter_gatilhos_negativos_contra_extra(self):
        return [
            "nao tenho contraproposta",
            "nao tenho contra proposta",
            "nao ha valor",
            "sem contraproposta",
            "sem contra proposta",
            "nao interessa",
            "deixa pra la",
            "deixa para la",
            "nao aceito",
        ]

    def iniciar_edge(self):
        """Abre o Edge depurável por meio do arquivo .bat."""
        st.info("🚀 Abrindo Edge depurável...")
        try:
            bat_path = APP_DIR / "abrir_whatsapp_edge.bat"

            if not bat_path.exists():
                st.error(f"❌ Arquivo .bat não encontrado em: {bat_path}")
                return False

            os.startfile(str(bat_path))
            time.sleep(3)

            st.success("✅ Comando para abrir o Edge foi executado!")
            return True

        except Exception as e:
            st.error(f"❌ Erro ao abrir Edge pelo .bat: {e}")
            return False
        
    def conectar_edge_debug(self):
        """Conecta ao Edge já aberto com depuração remota."""
        st.info("🔌 Tentando conectar ao Edge já aberto...")
        try:
            self.limpar_driver()

            edge_options = Options()
            edge_options.use_chromium = True
            edge_options.add_experimental_option("debuggerAddress", EDGE_DEBUG_HOST)

            self.driver = webdriver.Edge(options=edge_options)
            self.wait = WebDriverWait(self.driver, 25)

            st.success("✅ Conectado ao Edge depurável!")
            return True

        except Exception as e:
            self.limpar_driver()
            st.error(f"❌ Não foi possível conectar ao Edge em {EDGE_DEBUG_HOST}: {e}")
            return False
    
    def verificar_login(self):
        """Conecta ao Edge depurável e verifica o login no WhatsApp."""
        st.info("🔍 Verificando sessão do WhatsApp...")

        try:
            if not self.driver:
                conectou = self.conectar_edge_debug()
                if not conectou:
                    st.warning("⚠️ Abra primeiro o Edge pelo arquivo .bat.")
                    return False

            try:
                driver = self.driver
                driver.get("https://web.whatsapp.com")
            except (InvalidSessionIdException, WebDriverException):
                st.warning("⚠️ Sessão anterior do Edge ficou inválida. Reconectando...")
                conectou = self.conectar_edge_debug()
                if not conectou:
                    return False
                driver = self.driver
                driver.get("https://web.whatsapp.com")

            time.sleep(1.2)

            elementos_logado = [
                '//div[@data-testid="chat-list"]',
                '//div[@title="Caixa de texto de mensagem"]',
                '//div[@contenteditable="true"][@data-tab="3"]',
            ]

            for elemento in elementos_logado:
                try:
                    if driver.find_elements(By.XPATH, elemento):
                        st.success("✅ WhatsApp já está logado e pronto para uso!")
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.limpar_driver()
            st.error(f"❌ Erro ao verificar login: {e}")
            return False

    def limpar_driver(self):
        """Limpa a referência local do driver."""
        self.driver = None
        self.wait = None

    def enviar_mensagem_para_numero(self, telefone, mensagem):
        """Envia uma mensagem para um número específico."""
        try:
            if not self.driver:
                return False, "Edge não iniciado"

            telefone_limpo = re.sub(r"\D", "", str(telefone).strip())
            if len(telefone_limpo) != 13:
                return False, f"Telefone inválido: {telefone_limpo}"

            url = f"https://web.whatsapp.com/send?phone={telefone_limpo}&text={urllib.parse.quote(mensagem)}"
            self.driver.get(url)

            sucesso_envio = self.enviar_texto()

            if sucesso_envio:
                return True, "Mensagem enviada com sucesso"

            return False, "Falha ao clicar/enviar no chat do número"

        except Exception as e:
            return False, f"Erro ao enviar mensagem: {e}"

    def ler_ultimas_respostas_chat(self, limite=5):
        """Lê somente as mensagens recebidas após a última mensagem enviada por nós."""
        try:
            if not self.driver:
                return []

            time.sleep(1)

            mensagens_chat = self.driver.find_elements(
                By.XPATH,
                '//div[contains(@class,"message-in") or contains(@class,"message-out")]'
            )

            if not mensagens_chat:
                return []

            indice_ultima_out = None

            for i in range(len(mensagens_chat) - 1, -1, -1):
                try:
                    classes = (mensagens_chat[i].get_attribute("class") or "").lower()
                    if "message-out" in classes:
                        indice_ultima_out = i
                        break
                except Exception:
                    continue

            if indice_ultima_out is None:
                return []

            mensagens_recebidas = []

            for msg in mensagens_chat[indice_ultima_out + 1:]:
                try:
                    classes = (msg.get_attribute("class") or "").lower()
                    if "message-in" not in classes:
                        continue

                    texto_msg = (msg.text or "").strip()
                    if not texto_msg:
                        continue

                    linhas = [linha.strip() for linha in texto_msg.splitlines() if linha.strip()]
                    if not linhas:
                        continue

                    linhas_filtradas = []
                    for linha in linhas:
                        if re.fullmatch(r"\d{1,2}:\d{2}", linha):
                            continue
                        if linha in {"✓", "✓✓", "✓✓ lida"}:
                            continue
                        linhas_filtradas.append(linha)

                    if not linhas_filtradas:
                        continue

                    texto_final = " ".join(linhas_filtradas).strip()
                    if texto_final:
                        mensagens_recebidas.append(texto_final)

                except Exception:
                    continue

            if not mensagens_recebidas:
                return []

            return mensagens_recebidas[-limite:]

        except Exception:
            return []

    def normalizar_resposta(self, texto):
        """Normaliza retorno do cliente."""
        if not texto:
            return None

        t = texto.strip().upper()
        t = re.sub(r"\s+", " ", t)

        if t in {"1", "SIM", "1 - SIM", "1- SIM", "1 – SIM"}:
            return "SIM"

        if t in {"2", "NAO", "NÃO", "2 - NÃO", "2- NÃO", "2 – NÃO", "2 - NAO", "2- NAO"}:
            return "NÃO"

        return None


    def verificar_retornos(self, banco):
        """Verifica retornos das fases 1 e 2."""
        try:
            if not self.driver:
                return False, "Edge não iniciado"

            casos = self.carregar_casos()

            if banco not in casos or not casos[banco]:
                return True, "Nenhum caso cadastrado"

            casos_fase_1 = [
                (caso_id, caso)
                for caso_id, caso in casos[banco].items()
                if caso.get("fase") == 1
            ]

            casos_fase_2 = [
                (caso_id, caso)
                for caso_id, caso in casos[banco].items()
                if caso.get("fase") == 2
            ]

            processados_fase_1 = 0
            processados_fase_2 = 0
            leads_enviadas = 0
            recusados = 0
            contra_enviadas = 0
            sem_retorno = 0
            acima_alcada = 0

            # =====================================
            # FASE 1 -> interesse direto ou negativa
            # =====================================
            for caso_id, caso in casos_fase_1:
                telefone_destinatario, nome_destinatario = self.obter_telefone_destinatario(caso)

                if not telefone_destinatario:
                    sem_retorno += 1
                    continue

                url = f"https://web.whatsapp.com/send?phone={telefone_destinatario}"
                self.driver.get(url)
                time.sleep(5)

                ultimas_mensagens = self.ler_ultimas_respostas_chat(5)

                if not ultimas_mensagens:
                    sem_retorno += 1
                    continue

                texto_ultima_resposta = ultimas_mensagens[-1].strip()
                classificacao = self.classificar_resposta_inicial(texto_ultima_resposta)

                if not classificacao:
                    sem_retorno += 1
                    continue

                casos[banco][caso_id]["resposta_texto"] = texto_ultima_resposta
                casos[banco][caso_id]["data_resposta"] = datetime.now().strftime("%d/%m/%Y %H:%M")

                if classificacao == "POSITIVO":
                    valor_base = casos[banco][caso_id].get("valor_proposta_inicial")
                    if valor_base is None:
                        valor_base = self.calcular_proposta_inicial(caso)
                        casos[banco][caso_id]["valor_proposta_inicial"] = valor_base

                    sucesso_lead, _ = self.enviar_lead(
                        caso=caso,
                        telefone_destinatario=telefone_destinatario,
                        nome_destinatario=nome_destinatario,
                        valor_referencia=valor_base,
                        origem="proposta inicial"
                    )

                    if sucesso_lead:
                        casos[banco][caso_id]["fase"] = 3
                        casos[banco][caso_id]["lead_enviada"] = True
                        casos[banco][caso_id]["data_lead"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                        leads_enviadas += 1
                        processados_fase_1 += 1

                elif classificacao == "NEGATIVO":
                    msg_contra = f"Entendo. {nome_destinatario} teria alguma contra proposta pra fazer? Qual valor?"
                    sucesso_msg, _ = self.enviar_mensagem_para_numero(telefone_destinatario, msg_contra)

                    if sucesso_msg:
                        casos[banco][caso_id]["fase"] = 2
                        casos[banco][caso_id]["data_envio_contra"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                        contra_enviadas += 1
                        processados_fase_1 += 1

                self.salvar_casos(banco, casos[banco])

            # =====================================
            # FASE 2 -> contra proposta ou recusa final
            # =====================================
            for caso_id, caso in casos_fase_2:
                telefone_destinatario, nome_destinatario = self.obter_telefone_destinatario(caso)

                if not telefone_destinatario:
                    sem_retorno += 1
                    continue

                url = f"https://web.whatsapp.com/send?phone={telefone_destinatario}"
                self.driver.get(url)
                time.sleep(5)

                ultimas_mensagens = self.ler_ultimas_respostas_chat(5)

                if not ultimas_mensagens:
                    sem_retorno += 1
                    continue

                texto_ultima_resposta = ultimas_mensagens[-1].strip()

                if not texto_ultima_resposta:
                    sem_retorno += 1
                    continue

                casos[banco][caso_id]["contra_proposta_texto"] = texto_ultima_resposta
                casos[banco][caso_id]["data_resposta"] = datetime.now().strftime("%d/%m/%Y %H:%M")

                aguardando_resposta_90 = casos[banco][caso_id].get("aguardando_resposta_90", False)

                # =====================================================
                # CENÁRIO 1: ainda estamos esperando a CONTRAPROPOSTA
                # =====================================================
                if not aguardando_resposta_90:
                    retorno_fase_2 = self.classificar_resposta_contra(texto_ultima_resposta)

                    if retorno_fase_2 is None:
                        sem_retorno += 1
                        self.salvar_casos(banco, casos[banco])
                        continue

                    if retorno_fase_2 == "NEGATIVO":
                        casos[banco][caso_id]["fase"] = 5
                        casos[banco][caso_id]["aguardando_resposta_90"] = False
                        recusados += 1
                        processados_fase_2 += 1
                        self.salvar_casos(banco, casos[banco])
                        continue

                    if retorno_fase_2 == "POSITIVO":
                        valor_referencia = casos[banco][caso_id].get("valor_proposta_inicial")
                        if valor_referencia is None:
                            valor_referencia = self.calcular_proposta_inicial(caso)
                            casos[banco][caso_id]["valor_proposta_inicial"] = valor_referencia

                        sucesso_lead, _ = self.enviar_lead(
                            caso=caso,
                            telefone_destinatario=telefone_destinatario,
                            nome_destinatario=nome_destinatario,
                            valor_referencia=valor_referencia,
                            origem="aceite após negociação"
                        )

                        if sucesso_lead:
                            casos[banco][caso_id]["fase"] = 3
                            casos[banco][caso_id]["lead_enviada"] = True
                            casos[banco][caso_id]["data_lead"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                            casos[banco][caso_id]["aguardando_resposta_90"] = False
                            leads_enviadas += 1
                            processados_fase_2 += 1

                        self.salvar_casos(banco, casos[banco])
                        continue

                    valor_contra = float(retorno_fase_2)
                    alcada = self.converter_valor_brl_para_float(caso.get("alcada_maxima", "0"))
                    casos[banco][caso_id]["contra_proposta_valor"] = valor_contra

                    if valor_contra <= alcada:
                        sucesso_lead, _ = self.enviar_lead(
                            caso=caso,
                            telefone_destinatario=telefone_destinatario,
                            nome_destinatario=nome_destinatario,
                            valor_referencia=valor_contra,
                            origem="contra proposta"
                        )

                        if sucesso_lead:
                            casos[banco][caso_id]["fase"] = 3
                            casos[banco][caso_id]["lead_enviada"] = True
                            casos[banco][caso_id]["data_lead"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                            casos[banco][caso_id]["aguardando_resposta_90"] = False
                            leads_enviadas += 1
                            processados_fase_2 += 1

                        self.salvar_casos(banco, casos[banco])
                        continue

                    valor_limite_final = self.calcular_limite_final(caso)
                    valor_limite_formatado = self.formatar_valor_brl(valor_limite_final)

                    msg_limite = (
                        f"Infelizmente nesse valor não conseguimos, "
                        f"nosso limite é {valor_limite_formatado}. "
                        f"Há interesse nesse valor?"
                    )

                    sucesso_msg, _ = self.enviar_mensagem_para_numero(telefone_destinatario, msg_limite)

                    if sucesso_msg:
                        casos[banco][caso_id]["fase"] = 2
                        casos[banco][caso_id]["valor_limite_final"] = valor_limite_final
                        casos[banco][caso_id]["aguardando_resposta_90"] = True
                        casos[banco][caso_id]["ultimo_texto_lido_fase_2"] = texto_ultima_resposta
                        acima_alcada += 1
                        processados_fase_2 += 1

                    self.salvar_casos(banco, casos[banco])
                    continue

                # =====================================================
                # CENÁRIO 2: já foi enviada a proposta de 90%
                # agora só pode ir para LEAD ou RECUSADOS após
                # resposta positiva ou negativa
                # =====================================================
                classificacao_final = self.classificar_resposta_inicial(texto_ultima_resposta)

                if classificacao_final is None:
                    sem_retorno += 1
                    self.salvar_casos(banco, casos[banco])
                    continue

                if classificacao_final == "POSITIVO":
                    valor_referencia = casos[banco][caso_id].get("valor_limite_final")
                    if valor_referencia is None:
                        valor_referencia = self.calcular_limite_final(caso)

                    sucesso_lead, _ = self.enviar_lead(
                        caso=caso,
                        telefone_destinatario=telefone_destinatario,
                        nome_destinatario=nome_destinatario,
                        valor_referencia=valor_referencia,
                        origem="aceite após limite final"
                    )

                    if sucesso_lead:
                        casos[banco][caso_id]["fase"] = 3
                        casos[banco][caso_id]["lead_enviada"] = True
                        casos[banco][caso_id]["data_lead"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                        casos[banco][caso_id]["aguardando_resposta_90"] = False
                        leads_enviadas += 1
                        processados_fase_2 += 1

                    self.salvar_casos(banco, casos[banco])
                    continue

                if classificacao_final == "NEGATIVO":
                    casos[banco][caso_id]["fase"] = 5
                    casos[banco][caso_id]["aguardando_resposta_90"] = False
                    recusados += 1
                    processados_fase_2 += 1
                    self.salvar_casos(banco, casos[banco])
                    continue

            return True, (
                f"Verificação concluída | "
                f"Fase 1 processados: {processados_fase_1} | "
                f"Fase 2 processados: {processados_fase_2} | "
                f"Contra propostas enviadas: {contra_enviadas} | "
                f"Leads enviadas: {leads_enviadas} | "
                f"Recusados: {recusados} | "
                f"Contra proposta acima da alçada: {acima_alcada} | "
                f"Sem retorno lido: {sem_retorno}"
            )

        except Exception as e:
            return False, f"Erro ao verificar retornos: {e}"
    
    def enviar_mensagem_caso(self, banco):
        """Envia apenas 1 mensagem inicial por contato, se não houver outro caso desse contato na fase 1 ou 2."""
        try:
            casos = self.carregar_casos()

            if banco not in casos or not casos[banco]:
                return False, "Nenhum caso cadastrado"

            itens_casos = list(casos[banco].items())

            casos_fase_0 = []
            telefones_bloqueados = set()

            for caso_id, caso in itens_casos:
                telefone_destinatario, nome_destinatario = self.obter_telefone_destinatario(caso)

                if not telefone_destinatario:
                    continue

                if caso.get("fase", 0) in [1, 2]:
                    telefones_bloqueados.add(telefone_destinatario)

                elif caso.get("fase", 0) == 0:
                    casos_fase_0.append((caso_id, caso, telefone_destinatario, nome_destinatario))

            if not casos_fase_0:
                return True, "Nenhum caso na fase 0 para envio"

            enviados = 0
            falhas = 0
            bloqueados = 0
            enviados_por_telefone = set()

            for caso_id, caso, telefone_destinatario, nome_destinatario in casos_fase_0:
                if telefone_destinatario in telefones_bloqueados:
                    bloqueados += 1
                    continue

                if telefone_destinatario in enviados_por_telefone:
                    bloqueados += 1
                    continue

                driver = self.driver
                if not driver:
                    return False, "Edge não iniciado"

                processo_valor = caso.get("processo", "N/A")
                nome_parte = caso.get("nome_caso", "N/A")
                proposta_inicial = self.calcular_proposta_inicial(caso)
                proposta_formatada = self.formatar_valor_brl(proposta_inicial)

                mensagem_completa = f"""Olá {nome_destinatario}, entro em contato em função do processo {processo_valor}, de {nome_parte}.

                Temos uma proposta de acordo para este caso no valor de {proposta_formatada}.

                Há interesse na composição do acordo?"""

                url = f"https://web.whatsapp.com/send?phone={telefone_destinatario}&text={urllib.parse.quote(mensagem_completa)}"
                driver.get(url)

                if self.enviar_texto():
                    casos[banco][caso_id]["fase"] = 1
                    casos[banco][caso_id]["data_envio"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                    casos[banco][caso_id]["valor_proposta_inicial"] = proposta_inicial
                    self.salvar_casos(banco, casos[banco])

                    enviados += 1
                    enviados_por_telefone.add(telefone_destinatario)
                else:
                    falhas += 1

                time.sleep(1)

            return True, (
                f"Envio concluído | Enviados: {enviados} | "
                f"Bloqueados por contato já em atendimento: {bloqueados} | Falhas: {falhas}"
            )

        except Exception as e:
            return False, f"Erro ao enviar mensagens iniciais: {e}"

    def enviar_texto(self):
        """Confirma o envio da mensagem no chat atual clicando direto no botão enviar."""
        try:
            driver = self.driver
            wait = WebDriverWait(driver, 8)

            if not driver:
                return False

            seletores_botao = [
                '//button[@aria-label="Enviar"]',
                '//span[@data-icon="send"]/ancestor::button',
                '//button[.//span[@data-icon="send"]]',
            ]

            for seletor in seletores_botao:
                try:
                    botao_enviar = wait.until(
                        EC.element_to_be_clickable((By.XPATH, seletor))
                    )
                    botao_enviar.click()
                    return True
                except Exception:
                    continue

            seletores_caixa = [
                '//div[@title="Caixa de texto de mensagem"]',
                '//footer//div[@contenteditable="true"][@data-tab]',
                '//footer//div[@role="textbox"]',
                '//div[@role="textbox"]',
            ]

            for seletor in seletores_caixa:
                try:
                    caixa_mensagem = wait.until(
                        EC.element_to_be_clickable((By.XPATH, seletor))
                    )
                    caixa_mensagem.click()
                    caixa_mensagem.send_keys(Keys.ENTER)
                    return True
                except Exception:
                    continue

            return False

        except Exception:
            return False
    
# =========================
# 7) FUNÇÕES AUXILIARES
# =========================
def gerar_chave_unica(*args):
    """Gera uma chave única baseada nos argumentos fornecidos."""
    string_base = "_".join(str(arg) for arg in args)
    return hashlib.md5(string_base.encode()).hexdigest()[:10]


def filtrar_contatos_por_nome(contatos, termo_busca):
    """Filtra contatos pelo nome."""
    if not termo_busca:
        return contatos

    termo_busca = termo_busca.lower()
    contatos_filtrados = {}

    for contato_id, dados in contatos.items():
        if termo_busca in dados["nome"].lower():
            contatos_filtrados[contato_id] = dados

    return contatos_filtrados

def botao_liberar_edicao_contato(contato_id, idx):
    """Libera salvar/apagar contato mediante senha."""
    key_base = gerar_chave_unica("editar_contato", contato_id, idx)

    key_liberado = f"edicao_contato_liberada_{key_base}"
    key_pedir_senha = f"pedir_senha_contato_{key_base}"
    key_senha = f"senha_edicao_contato_{key_base}"

    if key_liberado not in st.session_state:
        st.session_state[key_liberado] = False

    if key_pedir_senha not in st.session_state:
        st.session_state[key_pedir_senha] = False

    if st.session_state[key_liberado]:
        col_status, col_bloquear, col_vazio = st.columns([0.25, 0.20, 0.55])

        with col_status:
            st.caption("🔓 Edição liberada")

        with col_bloquear:
            if st.button("🔒 Bloquear", key=f"btn_bloquear_edicao_{key_base}"):
                st.session_state[key_liberado] = False
                st.session_state[key_pedir_senha] = False
                st.rerun()

        return True

    col_btn, col_senha, col_liberar, col_vazio = st.columns([0.16, 0.38, 0.18, 0.28])

    with col_btn:
        if st.button("🔐 Editar", key=f"btn_pedir_senha_{key_base}", help="Liberar edição do contato"):
            st.session_state[key_pedir_senha] = not st.session_state[key_pedir_senha]
            st.rerun()

    if st.session_state[key_pedir_senha]:
        with col_senha:
            senha_digitada = st.text_input(
                "Senha",
                type="password",
                key=key_senha,
                placeholder="Digite a senha",
                label_visibility="collapsed",
            )

        with col_liberar:
            if st.button("Liberar", key=f"btn_liberar_edicao_{key_base}"):
                if senha_digitada == "senha":
                    st.session_state[key_liberado] = True
                    st.session_state[key_pedir_senha] = False
                    st.rerun()
                else:
                    st.error("Senha incorreta")

    return False

def gerar_excel_casos(lista_casos):
    """Gera arquivo Excel em memória com os dados dos casos."""
    dados_excel = []

    for caso_id, caso in lista_casos:
        fase_numero = caso.get("fase", 0)
        fase_info = FASES_INFO.get(fase_numero, FASES_INFO[0])

        dados_excel.append({
            "ID Caso": caso_id,
            "Nome do Caso": caso.get("nome_caso", ""),
            "Contato": caso.get("nome", ""),
            "Telefone": caso.get("telefone", ""),
            "Tipo": caso.get("tipo", ""),
            "OAB": caso.get("oab", ""),
            "CPF": caso.get("cpf", ""),
            "GCPJ": caso.get("identificador", ""),
            "Processo": caso.get("processo", ""),
            "Alçada Máxima": caso.get("alcada_maxima", ""),
            "Fase Nº": fase_numero,
            "Fase": fase_info["nome"],
            "Resposta": caso.get("resposta", ""),
            "Data Cadastro": caso.get("data_cadastro", ""),
            "Data Envio": caso.get("data_envio", ""),
            "Data Resposta": caso.get("data_resposta", ""),
            "Negociador": caso.get("negociador", ""),
            "Minuta Enviada": caso.get("minuta_enviada", False),
        })

    df = pd.DataFrame(dados_excel)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Casos")

    output.seek(0)
    return output

@st.dialog("Editar contato")
def modal_editar_contato(bot, contato_id, dados, idx):
    key_base = gerar_chave_unica("modal_editar_contato", contato_id, idx)
    key_acao_pendente = f"acao_pendente_contato_{key_base}"

    if key_acao_pendente not in st.session_state:
        st.session_state[key_acao_pendente] = None

    with st.form(f"form_modal_editar_contato_{key_base}"):
        col1, col2 = st.columns(2)

        with col1:
            novo_nome = st.text_input(
                "Nome",
                value=dados["nome"],
                key=f"modal_edit_nome_{contato_id}_{idx}"
            )

            novo_telefone = st.text_input(
                "Telefone",
                value=dados.get("telefone", ""),
                key=f"modal_edit_tel_{contato_id}_{idx}",
                help="Formato: 55XX9XXXXXXXX (13 dígitos)",
            )

            novo_celular = st.text_input(
                "Celular",
                value=dados.get("celular", "") or "",
                key=f"modal_edit_celular_{contato_id}_{idx}",
                help="Formato: 55XX9XXXXXXXX (13 dígitos)",
            )

            novo_email = st.text_input(
                "E-mail",
                value=dados.get("email", ""),
                key=f"modal_edit_email_{contato_id}_{idx}"
            )

        with col2:
            nova_oab = st.text_input(
                "OAB",
                value=dados.get("oab", "") or "",
                key=f"modal_edit_oab_{contato_id}_{idx}"
            )

            nova_uf_oab = st.text_input(
                "UF OAB",
                value=dados.get("uf_oab", "MG") or "MG",
                max_chars=2,
                key=f"modal_edit_uf_oab_{contato_id}_{idx}"
            )

            novo_cpf = st.text_input(
                "CPF",
                value=dados.get("cpf", "") or "",
                key=f"modal_edit_cpf_{contato_id}_{idx}"
            )

        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            salvar = st.form_submit_button("💾 Salvar Alterações", use_container_width=True)

        with col_btn2:
            apagar = st.form_submit_button("🗑️ Apagar Contato", use_container_width=True)

    if salvar:
        st.session_state[key_acao_pendente] = "salvar"

    if apagar:
        st.session_state[key_acao_pendente] = "apagar"

    if st.session_state[key_acao_pendente]:
        st.markdown("---")

        acao = st.session_state[key_acao_pendente]

        if acao == "salvar":
            st.warning("Digite a senha para confirmar as alterações.")
        else:
            st.warning("Digite a senha para confirmar a exclusão do contato.")

        senha_digitada = st.text_input(
            "Senha",
            type="password",
            key=f"senha_confirmacao_contato_{key_base}",
            placeholder="Digite a senha",
        )

        col_confirmar, col_cancelar = st.columns(2)

        with col_confirmar:
            if st.button("Confirmar", key=f"btn_confirmar_acao_contato_{key_base}", use_container_width=True):
                if senha_digitada != "senha":
                    st.error("Senha incorreta")
                    return

                if acao == "salvar":
                    sucesso, mensagem = bot.editar_contato(
                        contato_id,
                        novo_nome,
                        novo_telefone,
                        novo_celular,
                        novo_email,
                        nova_oab,
                        novo_cpf,
                        nova_uf_oab
                    )

                    if sucesso:
                        st.session_state[key_acao_pendente] = None
                        st.success(mensagem)
                        st.rerun()
                    else:
                        st.error(mensagem)

                elif acao == "apagar":
                    contatos = bot.carregar_contatos()

                    if contato_id in contatos:
                        del contatos[contato_id]

                        if bot.salvar_contatos(contatos):
                            st.session_state[key_acao_pendente] = None
                            st.success("✅ Contato apagado com sucesso!")
                            st.rerun()
                        else:
                            st.error("❌ Erro ao apagar contato")

        with col_cancelar:
            if st.button("Cancelar", key=f"btn_cancelar_acao_contato_{key_base}", use_container_width=True):
                st.session_state[key_acao_pendente] = None
                st.rerun()
# =========================
# 8) TELA INICIAL
# =========================
def mostrar_tela_inicial():
    """Tela inicial com imagens lado a lado e botões clicáveis."""

    logo_bradesco_base64 = image_to_base64(LOGO_BRADESCO)

    st.markdown("""
        <style>
        div[data-testid="stButton"] > button[kind="secondary"] {
            height: 53px !important;
            font-size: 40px !important;
            font-weight: bold !important;
            border-radius: 15px !important;
            background: radial-gradient(ellipse, #D1D5DB 0%, #6B7280 100%) !important;
            border: 3px solid #4B5563 !important;
            min-width: 233px !important;
            width: 40% !important;
            display: block !important;
            margin: 10px auto !important;
            padding: 0 !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2) !important;
            transition: all 0.3s ease !important;
        }

        div[data-testid="stButton"] > button[kind="secondary"] > div {
            width: 100% !important;
            height: 100% !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        div[data-testid="stButton"] > button[kind="secondary"] > div > p {
            width: 100% !important;
            height: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            font-size: 17px !important;
            font-weight: bold !important;
        }

        div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background: radial-gradient(circle, #6B7280 0%, #374151 100%) !important;
            border-color: #374151 !important;
            transform: translateY(-4px) scale(1.02) !important;
            box-shadow: 0 8px 25px rgba(0,0,0,0.3) !important;
        }
        </style>
        """, unsafe_allow_html=True)

    st.markdown(f"""
        <div style="text-align: center; padding: 2rem; background: linear-gradient(90deg, #EC7000 0%, #CC092F 100%);
                    border-radius: 20px; color: white; margin-bottom: 3rem;">
            <h1>🤖 Ribeiro de Andrade - Gestão de Acordos</h1>
            <p style="font-size: 1.2rem; margin-bottom: 8px;">
                Sistema inteligente para gestão de acordos
            </p>
        </div>
        """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        if logo_bradesco_base64:
            st.markdown(f'''
            <div style="text-align: center; margin-bottom: 20px;">
                <img src="data:image/png;base64,{logo_bradesco_base64}"
                    style="width: 280px; height: 280px; object-fit: contain;">
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.info("Logo Bradesco não encontrada")

        if st.button("GESTÃO ACORDOS BRADESCO", key="btn_bradesco", use_container_width=True):
            st.session_state.banco_selecionado = "BRADESCO"
            st.session_state.pagina = "📋 CASOS"
            st.rerun()


# =========================
# 9) EXIBIÇÃO DE CASOS
# =========================
def mostrar_caso_com_moldura(caso, caso_id, banco, bot, contexto="", destaque_fase=False):
    """Mostra um caso já com os detalhes visíveis e edição recolhida por botão."""
    key_suffix = gerar_chave_unica(caso_id, banco, contexto)

    fase_info = FASES_INFO.get(caso.get("fase", 0), FASES_INFO[0]).copy()

    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write(f"**👤 Contato:** {caso['nome']}")
        st.write(f"**📞 Telefone:** {caso['telefone']}")
        if caso.get("email"):
            st.write(f"**📧 E-mail:** {caso['email']}")
        st.write(f"**📋 Tipo:** {caso['tipo']}")
        if caso.get("oab"):
            st.write(f"**⚖️ OAB:** {caso['oab']}")
        if caso.get("cpf"):
            st.write(f"**🆔 CPF:** {caso['cpf']}")

    with col2:
        st.write(f"**🔢 {LABEL_IDENTIFICADOR}:** {caso.get('identificador', 'N/A')}")
        st.write(f"**📄 {LABEL_PROCESSO}:** {caso.get('processo', 'N/A')}")
        st.write(f"**🏛️ {LABEL_VARA}:** {caso.get('numero_orgao', 'N/A')}")
        st.write(f"**⚖️ {LABEL_ORGAO}:** {caso.get('tipo_orgao', 'N/A')}")
        st.write(f"**📍 {LABEL_COMARCA}:** {caso.get('comarca', 'N/A')}")
        st.write(f"**💰 {LABEL_ALCADA}:** {caso.get('alcada_maxima', '') or 'N/A'}")
        st.write(f"**📅 Data Cadastro:** {caso['data_cadastro']}")

    with col3:
        st.write(f"**📌 Fase Atual:** {fase_info['nome']}")

        if caso.get("data_envio"):
            st.write(f"**📤 Msg Enviada:** {caso['data_envio']}")

        if caso.get("data_resposta"):
            resposta_texto = caso.get("contra_proposta_texto") or caso.get("resposta_texto", "")
            st.write(f"**📅 Data Resposta:** {caso['data_resposta']}. {resposta_texto}")

        if caso.get("negociador"):
            st.write(f"**👤 Negociador:** {caso['negociador']}")
        
        if caso.get("valor_proposta_inicial") is not None:
            st.write(f"**💵 Proposta Inicial:** {bot.formatar_valor_brl(caso['valor_proposta_inicial'])}")

        if caso.get("data_envio_contra"):
            st.write(f"**↩️ Contra enviada em:** {caso['data_envio_contra']}")

        if caso.get("contra_proposta_valor") is not None:
            st.write(f"**💰 Contra proposta:** {bot.formatar_valor_brl(caso['contra_proposta_valor'])}")

        if caso.get("data_lead"):
            st.write(f"**📨 Lead enviada em:** {caso['data_lead']}")

    st.markdown("---")

    chave_edicao = f"mostrar_edicao_{key_suffix}"
    if chave_edicao not in st.session_state:
        st.session_state[chave_edicao] = False

    col_btn_editar, col_fase1, col_fase2 = st.columns([.9, 1.3, 0.9])

    with col_btn_editar:
        if st.button("✏️ Editar Caso", key=f"btn_mostrar_edicao_{key_suffix}"):
            st.session_state[chave_edicao] = not st.session_state[chave_edicao]
            st.rerun()

    with col_fase1:
        nova_fase = st.selectbox(
            "Alterar Fase:",
            options=[
                (0, f"{FASE_0_COR} FASE 0 - {FASE_0}"),
                (1, f"{FASE_1_COR} FASE 1 - {FASE_1}"),
                (2, f"{FASE_2_COR} FASE 2 - {FASE_2}"),
                (3, f"{FASE_3_COR} FASE 3 - {FASE_3}"),
                (4, f"{FASE_4_COR} FASE 4 - {FASE_4}"),
                (5, f"{FASE_5_COR} FASE 5 - {FASE_5}"),
                (6, f"{FASE_6_COR} FASE 6 - {FASE_6}"),
            ],
            format_func=lambda x: x[1],
            index=caso.get("fase", 0),
            key=f"select_fase_{key_suffix}",
            label_visibility="collapsed",
        )

    with col_fase2:
        if st.button("🔄 Atualizar Fase", key=f"btn_fase_{key_suffix}", use_container_width=True):
            sucesso, mensagem = bot.atualizar_fase_caso(
                banco,
                caso_id,
                nova_fase[0]
            )
            if sucesso:
                st.success(mensagem)
                st.rerun()
            else:
                st.error(mensagem)

    if st.session_state[chave_edicao]:
        st.markdown("---")

        edit_nome_caso = st.text_input(
            LABEL_NOME_CASO,
            value=caso.get("nome_caso", ""),
            key=f"edit_nome_caso_{key_suffix}"
        )

        edit_identificador = st.text_input(
            LABEL_IDENTIFICADOR,
            value=caso.get("identificador", ""),
            key=f"edit_identificador_{key_suffix}"
        )

        edit_processo = st.text_input(
            LABEL_PROCESSO,
            value=caso.get("processo", ""),
            key=f"edit_processo_{key_suffix}"
        )

        comarcas_mg = carregar_comarcas_mg()

        col_edit_org1, col_edit_org2, col_edit_org3 = st.columns(3)

        with col_edit_org1:
            edit_numero_orgao = st.selectbox(
                LABEL_VARA,
                options=list(range(1, 51)),
                index=max(0, int(caso.get("numero_orgao", 1)) - 1) if str(caso.get("numero_orgao", "")).isdigit() else 0,
                key=f"edit_numero_orgao_{key_suffix}"
            )

        with col_edit_org2:
            opcoes_tipo_orgao = ["Vara Cível", "Juizado Especial"]
            valor_tipo_orgao = caso.get("tipo_orgao", "Vara Cível")
            edit_tipo_orgao = st.selectbox(
                LABEL_ORGAO,
                options=opcoes_tipo_orgao,
                index=opcoes_tipo_orgao.index(valor_tipo_orgao) if valor_tipo_orgao in opcoes_tipo_orgao else 0,
                key=f"edit_tipo_orgao_{key_suffix}"
            )

        with col_edit_org3:
            opcoes_comarca = comarcas_mg if comarcas_mg else [""]
            valor_comarca = caso.get("comarca", "")
            edit_comarca = st.selectbox(
                LABEL_COMARCA,
                options=opcoes_comarca,
                index=opcoes_comarca.index(valor_comarca) if valor_comarca in opcoes_comarca else 0,
                key=f"edit_comarca_{key_suffix}"
            )

        edit_alcada_maxima = st.text_input(
            LABEL_ALCADA,
            value=caso.get("alcada_maxima", ""),
            key=f"edit_alcada_{key_suffix}"
        )

        contatos = bot.carregar_contatos()
        opcoes_contato_edicao = list(contatos.keys())

        contato_atual_id = caso.get("contato_id")
        if contato_atual_id not in opcoes_contato_edicao and contato_atual_id is not None:
            opcoes_contato_edicao = [contato_atual_id] + opcoes_contato_edicao

        edit_contato_id = st.selectbox(
            "Contato do Caso",
            options=opcoes_contato_edicao,
            index=opcoes_contato_edicao.index(contato_atual_id) if contato_atual_id in opcoes_contato_edicao else 0,
            format_func=lambda x: f"{contatos[x]['nome']} - {contatos[x]['tipo']}" if x in contatos else "Contato atual",
            key=f"edit_contato_caso_{key_suffix}"
        )

        col_edit1, col_edit2 = st.columns(2)

        with col_edit1:
            if st.button("💾 Salvar Caso", key=f"btn_salvar_caso_{key_suffix}", use_container_width=True):
                sucesso, mensagem = bot.editar_caso(
                    banco,
                    caso_id,
                    nome_caso=edit_nome_caso.strip(),
                    identificador=re.sub(r"\D", "", edit_identificador),
                    processo=edit_processo.strip(),
                    numero_orgao=edit_numero_orgao,
                    tipo_orgao=edit_tipo_orgao,
                    comarca=edit_comarca,
                    alcada_maxima=edit_alcada_maxima.strip(),
                    contato_id=edit_contato_id,
                )
                if sucesso:
                    st.success(mensagem)
                    st.rerun()
                else:
                    st.error(mensagem)

        with col_edit2:
            if st.button("🗑️ Apagar Caso", key=f"btn_apagar_caso_{key_suffix}", use_container_width=True):
                sucesso, mensagem = bot.apagar_caso(banco, caso_id)
                if sucesso:
                    st.success(mensagem)
                    st.rerun()
                else:
                    st.error(mensagem)


# =========================
# 10) INTERFACE PRINCIPAL
# =========================
def main():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
        <style>
        div[role="radiogroup"] label {
            font-size: 22px !important;
            padding: 15px 10px !important;
            font-weight: 500 !important;
        }

        section[data-testid="stSidebar"] {
            min-width: 280px !important;
        }

        .sidebar-logo {
            text-align: center;
            margin-bottom: 20px;
        }
        </style>
        """, unsafe_allow_html=True)

    if "bot" not in st.session_state:
        st.session_state.bot = WhatsAppBotCorrigido()

    if "pagina" not in st.session_state:
        st.session_state.pagina = "🏠 INÍCIO"
    if "banco_selecionado" not in st.session_state:
        st.session_state.banco_selecionado = "BRADESCO"

    bot = st.session_state.bot

    if "auto_bot_ativo" not in st.session_state:
        st.session_state.auto_bot_ativo = False

    if "ultimo_ciclo_auto" not in st.session_state:
        st.session_state.ultimo_ciclo_auto = None

    if "ultimo_ciclo_auto_ts" not in st.session_state:
        st.session_state.ultimo_ciclo_auto_ts = None

    if "logs_auto_bot" not in st.session_state:
        st.session_state.logs_auto_bot = []

    with st.sidebar:
        logo_base64 = image_to_base64(LOGO_RA)

        if logo_base64:
            st.markdown(f"""
            <div class="sidebar-logo">
                <img src="data:image/png;base64,{logo_base64}"
                     style="width: 200px; height: 200px; object-fit: contain;">
            </div>
            """, unsafe_allow_html=True)
        else:
            st.title("🤖 RA")

        if st.session_state.pagina == "🏠 INÍCIO":
            st.session_state.banco_selecionado = None
            opcoes_menu = ["🏠 INÍCIO", "📞 CONTATOS"]
        else:
            if st.session_state.banco_selecionado:
                opcoes_menu = ["🏠 INÍCIO", "📋 CASOS", "📞 CONTATOS", "🤖 BOT WHATSAPP"]
            else:
                opcoes_menu = ["🏠 INÍCIO", "📞 CONTATOS"]

        st.markdown("""
            <style>
            div[role="radiogroup"] label {
                font-size: 26px !important;
                padding: 18px 12px !important;
                font-weight: 600 !important;
                min-height: 70px !important;
                display: flex !important;
                align-items: center !important;
                border-radius: 10px !important;
                margin: 5px 0 !important;
                transition: all 0.2s ease !important;
            }

            div[role="radiogroup"] label:hover {
                background-color: rgba(49, 51, 63, 0.1) !important;
            }

            div[role="radiogroup"] label[data-checked="true"] {
                background-color: rgba(49, 51, 63, 0.2) !important;
                border-left: 4px solid #FF4B4B !important;
            }

            .stRadio > label:first-child {
                font-size: 20px !important;
                font-weight: bold !important;
                margin-bottom: 15px !important;
            }
            </style>
            """, unsafe_allow_html=True)

        pagina = st.radio(
            "",
            opcoes_menu,
            index=opcoes_menu.index(st.session_state.pagina) if st.session_state.pagina in opcoes_menu else 0,
            key="sidebar_navigation",
        )

        if pagina != st.session_state.pagina:
            st.session_state.pagina = pagina
            st.rerun()

        st.markdown("---")

        if st.session_state.banco_selecionado and st.session_state.pagina != "🏠 INÍCIO":
            st.info(f"Banco selecionado: **{st.session_state.banco_selecionado}**")

    # =========================
    # 10.1) ROTEAMENTO
    # =========================
    if st.session_state.pagina == "🏠 INÍCIO":
        mostrar_tela_inicial()

    elif st.session_state.pagina == "📞 CONTATOS":
        total_contatos = len(bot.carregar_contatos())
        st.header(f"📞 Gestão de Contatos ({total_contatos} contatos cadastrados)")

        tab1, tab2 = st.tabs(["📝 Cadastrar", "📋 Listar/Editar"])

        with tab1:
            st.markdown("### 🆕 Adicionar Contato")

            col1, col2, col3 = st.columns(3)

            with col1:
                nome = st.text_input("📝 **NOME COMPLETO DO CONTATO**", placeholder="ex: João Silva")
                telefone = st.text_input("📞 **TELEFONE** (31 XXXXXXXX)", placeholder="ex: 31 30253464")
                celular = st.text_input("📱 **CELULAR** (55XX9XXXXXXXX - 13 dígitos)", placeholder="ex: 5531999999999")
                email = st.text_input("**E-MAIL** (opcional)", placeholder="ex: joao@email.com")

            with col2:
                oab = st.text_input(
                    "⚖️ **NÚMERO DA OAB**",
                    placeholder="111176",
                    help="Sempre cadastrar para o advogado"
                )

                uf_oab = st.text_input(
                    "🌎 **UF DA OAB**",
                    value="MG",
                    max_chars=2
                )

                cpf = st.text_input(
                    "🆔 **CPF AUTOR SEM ADV** (opcional para o advogado)",
                    placeholder="12345678900"
                )

            with col3:
                ""

            if st.button("💾 SALVAR CONTATO", type="primary", use_container_width=True):
                if not nome.strip():
                    st.error("❌ O campo Nome é obrigatório")
                elif not telefone.strip():
                    st.error("❌ O campo Telefone é obrigatório")
                elif not oab.strip() and not cpf.strip():
                    st.error("❌ É necessário preencher OAB ou CPF")
                else:
                    sucesso, mensagem = bot.adicionar_contato(
                        nome=nome.strip(),
                        telefone=telefone.strip(),
                        celular=celular.strip() if celular else "",
                        email=email.strip() if email else "",
                        oab=oab.strip() if oab else None,
                        cpf=cpf.strip() if cpf else None,
                        uf_oab=uf_oab.strip().upper() if uf_oab else "MG",
                    )

                    if sucesso:
                        st.success(f"""
🎉 **CONTATO CADASTRADO COM SUCESSO!**

**Nome:** {nome.strip()}
**Telefone:** {telefone.strip()}
**Celular:** {celular.strip() if celular else ''}
**Tipo:** {'Advogado' if oab.strip() else 'Cliente'}
**E-mail:** {email.strip() if email else ''}
**UF OAB:** {uf_oab.strip().upper() if oab.strip() else ''}
**Arquivo salvo em:** `{bot.arquivo_contatos}`
""")
                        st.balloons()
                    else:
                        st.error(f"❌ {mensagem}")

        with tab2:
            contatos = bot.carregar_contatos()

            if contatos:
                col_lupa, col_input = st.columns([0.03, 0.97])

                with col_lupa:
                    st.markdown(
                        "<div style='font-size: 28px; padding-top: 4px;'>🔍</div>",
                        unsafe_allow_html=True
                    )

                with col_input:
                    termo_busca = st.text_input(
                        "Buscar contato por nome",
                        placeholder="Digite o nome do contato...",
                        key="busca_contatos",
                        label_visibility="collapsed",
                    ).strip()

                if termo_busca:
                    contatos_filtrados = filtrar_contatos_por_nome(contatos, termo_busca)

                    if not contatos_filtrados:
                        st.warning(f"❌ Nenhum contato encontrado para '{termo_busca}'")
                    else:
                        contatos_ordenados = sorted(
                            contatos_filtrados.items(),
                            key=lambda x: x[1]["nome"].lower(),
                        )

                        for i in range(0, len(contatos_ordenados), 3):
                            col1, col2, col3 = st.columns(3)

                            pares = [(col1, i)]

                            if i + 1 < len(contatos_ordenados):
                                pares.append((col2, i + 1))

                            if i + 2 < len(contatos_ordenados):
                                pares.append((col3, i + 2))

                            for col, idx in pares:
                                contato_id, dados = contatos_ordenados[idx]

                                email_atual = dados.get("email", "") or ""

                                titulo_contato = f"{dados['nome']}"

                                if dados.get("tipo") and not dados.get("oab"):
                                    titulo_contato += f" - {dados['tipo']}"

                                if email_atual:
                                    titulo_contato += f" - {email_atual}"

                                with col:
                                    with st.expander(titulo_contato):
                                        col1, col2 = st.columns(2)

                                        with col1:
                                            st.markdown("**Nome**")
                                            st.write(dados.get("nome", "") or "-")

                                            st.markdown("**Telefone**")
                                            st.write(dados.get("telefone", "") or "-")

                                            st.markdown("**Celular**")
                                            st.write(dados.get("celular", "") or "-")

                                            st.markdown("**E-mail**")
                                            st.markdown(
                                                f"<div style='min-height: 20px; margin-bottom: 0;'>{dados.get('email', '') or '&nbsp;'}</div>",
                                                unsafe_allow_html=True
                                            )

                                        with col2:
                                            st.markdown("**OAB**")
                                            st.write(dados.get("oab", "") or "-")

                                            st.markdown("**UF OAB**")
                                            st.write(dados.get("uf_oab", "MG") or "-")

                                            st.markdown("**CPF**")
                                            st.markdown(
                                                f"<div style='min-height: 20px; margin-bottom: 0;'>{dados.get('cpf', '') or '&nbsp;'}</div>",
                                                unsafe_allow_html=True
                                            )

                                        if st.button("🔐 Editar", key=f"btn_modal_editar_contato_{contato_id}_{idx}"):
                                            modal_editar_contato(bot, contato_id, dados, idx)
            else:
                st.info("📭 Nenhum contato cadastrado")

    elif st.session_state.pagina == "📋 CASOS":
        if not st.session_state.banco_selecionado:
            st.warning("⚠️ Selecione um banco primeiro na página inicial")
            if st.button("🏠 Voltar para Início"):
                st.session_state.pagina = "🏠 INÍCIO"
                st.rerun()
        else:
            st.subheader(f"📋 Gestão de Casos - {st.session_state.banco_selecionado}")

            tab1, tab2, tab3 = st.tabs(["➕ Novo Caso", "📋 Lista de Casos", "📊 Visualização por Fase"])

            with tab1:
                st.markdown(f"### 🆕 Adicionar Caso - {st.session_state.banco_selecionado}")

                contatos = bot.carregar_contatos()

                if not contatos:
                    st.warning("📭 Nenhum contato cadastrado. Cadastre um contato primeiro.")
                else:
                    col1, col2 = st.columns(2)

                    with col2:
                        opcoes_contato = [""] + list(contatos.keys())
                        contato_selecionado = st.selectbox(
                            "Selecione o Contato*",
                            options=opcoes_contato,
                            format_func=lambda x: "Selecione..." if x == "" else f"{contatos[x]['nome']} - {contatos[x]['tipo']}",
                            key="novo_caso_contato",
                        )

                        st.markdown("**Informações do Contato:**")
                        if contato_selecionado != "":
                            contato_info = contatos[contato_selecionado]
                            st.write(f"Nome: {contato_info['nome']}")
                            st.write(f"Telefone: {contato_info.get('telefone', '') or '-'}")
                            st.write(f"Celular: {contato_info.get('celular', '') or '-'}")
                            st.write(f"E-mail: {contato_info.get('email', '') or '-'}")
                            st.write(f"Tipo: {contato_info['tipo']}")

                            if contato_info.get("oab"):
                                st.write(f"OAB: {contato_info.get('oab')}")
                                st.write(f"UF OAB: {contato_info.get('uf_oab', 'MG') or 'MG'}")

                            if contato_info.get("cpf"):
                                st.write(f"CPF: {contato_info['cpf']}")
                        else:
                            st.write("Nome: ")
                            st.write("Telefone: ")
                            st.write("Celular: ")
                            st.write("E-mail: ")
                            st.write("Tipo: ")
                            st.write("CPF/OAB: ")
                            st.write("UF OAB: ")

                    with col1:
                        with st.form("form_novo_caso"):
                            nome_caso = st.text_input(f"{LABEL_NOME_CASO}*", key="novo_caso_nome")

                            identificador_label = f"{LABEL_IDENTIFICADOR} (10 números)*"
                            processo = st.text_input(f"{LABEL_PROCESSO}*", key="novo_caso_processo")

                            identificador = st.text_input(
                                identificador_label,
                                key="novo_caso_identificador",
                                help=f"Digite o número {LABEL_IDENTIFICADOR} com 10 dígitos",
                            )

                            comarcas_mg = carregar_comarcas_mg()

                            col_proc1, col_proc2, col_proc3 = st.columns(3)

                            with col_proc1:
                                numero_orgao = st.selectbox(
                                    LABEL_VARA,
                                    options=list(range(1, 51)),
                                    key="novo_caso_numero_orgao"
                                )

                            with col_proc2:
                                tipo_orgao = st.selectbox(
                                    LABEL_ORGAO,
                                    options=["VARA CÍVEL", "JUIZADO ESPECIAL"],
                                    key="novo_caso_tipo_orgao"
                                )

                            with col_proc3:
                                comarca = st.selectbox(
                                    LABEL_COMARCA,
                                    options=comarcas_mg if comarcas_mg else [""],
                                    key="novo_caso_comarca"
                                )

                            alcada_maxima = st.text_input(
                                LABEL_ALCADA,
                                key="novo_caso_alcada",
                                placeholder="Ex: 5.000,00"
                            )

                            submitted = st.form_submit_button("💾 Adicionar Caso", key="btn_novo_caso")

                            if submitted:
                                if all([nome_caso, identificador, processo, contato_selecionado]):
                                    identificador_limpo = re.sub(r"\D", "", identificador)

                                    if len(identificador_limpo) != 10:
                                        st.error("❌ O GCPJ deve ter exatamente 10 números")
                                    else:
                                        sucesso, mensagem = bot.adicionar_caso(
                                            st.session_state.banco_selecionado,
                                            nome_caso.strip(),
                                            identificador_limpo,
                                            processo.strip(),
                                            contato_selecionado,
                                            alcada_maxima.strip(),
                                            numero_orgao,
                                            tipo_orgao,
                                            comarca,
                                        )
                                        if sucesso:
                                            st.success(mensagem)
                                        else:
                                            st.error(mensagem)
                                else:
                                    st.error("Preencha todos os campos obrigatórios (*)")


            with tab2:
               
                casos = bot.carregar_casos()
                banco = st.session_state.banco_selecionado

                if banco in casos and casos[banco]:
                    termo_busca_caso = st.text_input(
                        "🔍 Buscar caso",
                        placeholder="Digite nome do caso, nome do contato, GCPJ, processo, CPF ou telefone",
                        key="busca_casos"
                    ).strip().lower()

                    itens_casos = list(casos[banco].items())

                    if termo_busca_caso:
                        itens_filtrados = []

                        for caso_id, caso in itens_casos:
                            campos_busca = [
                                str(caso.get("nome_caso", "")),
                                str(caso.get("nome", "")),
                                str(caso.get("identificador", "")),
                                str(caso.get("processo", "")),
                                str(caso.get("cpf", "")),
                                str(caso.get("telefone", "")),
                            ]

                            texto_busca = " ".join(campos_busca).lower()

                            if termo_busca_caso in texto_busca:
                                itens_filtrados.append((caso_id, caso))

                        itens_casos = itens_filtrados

                    st.info(f"📊 Casos encontrados: {len(itens_casos)}")

                    if itens_casos:
                        for i in range(0, len(itens_casos), 2):
                            col1, col2 = st.columns(2)
                            pares = [(col1, i)]

                            if i + 1 < len(itens_casos):
                                pares.append((col2, i + 1))

                            for col, idx in pares:
                                caso_id, caso = itens_casos[idx]
                                fase_info = FASES_INFO.get(caso.get("fase", 0), FASES_INFO[0]).copy()

                                titulo_lista = f"{LABEL_IDENTIFICADOR}: {caso.get('identificador', 'N/A')} | {caso.get('nome_caso', caso.get('nome', 'Sem nome'))}"

                                with col:
                                    st.markdown(
                                        """
                                        <div style="margin-bottom: 8px;"></div>
                                        """,
                                        unsafe_allow_html=True
                                    )

                                    with st.expander(f"{fase_info['icone']} {titulo_lista}", expanded=False):
                                        mostrar_caso_com_moldura(
                                            caso,
                                            caso_id,
                                            banco,
                                            bot,
                                            f"lista_{idx}"
                                        )
                    else:
                        st.warning("Nenhum caso encontrado para o termo pesquisado.")
                else:
                    st.info(f"📭 Nenhum caso cadastrado para {banco}")

            with tab3:
                casos = bot.carregar_casos()
                banco = st.session_state.banco_selecionado

                if banco in casos and casos[banco]:
                    fases = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}

                    for caso_id, caso in casos[banco].items():
                        fases[caso.get("fase", 0)].append((caso_id, caso))

                    for numero_fase, titulo in [
                        (0, f"{FASE_0_COR} Fase 0 - {FASE_0}"),
                        (1, f"{FASE_1_COR} Fase 1 - {FASE_1}"),
                        (2, f"{FASE_2_COR} Fase 2 - {FASE_2}"),
                        (3, f"{FASE_3_COR} Fase 3 - {FASE_3}"),
                        (4, f"{FASE_4_COR} Fase 4 - {FASE_4}"),
                        (5, f"{FASE_5_COR} Fase 5 - {FASE_5}"),
                        (6, f"{FASE_6_COR} Fase 6 - {FASE_6}"),
                    ]:
                        casos_fase = fases[numero_fase]

                        col_titulo, col_download = st.columns([3, 1])

                        with col_titulo:
                            st.markdown(f"### {titulo} ({len(casos_fase)})")

                        with col_download:
                            if casos_fase:
                                excel_fase = gerar_excel_casos(casos_fase)
                                st.download_button(
                                    label="📥 Download Excel",
                                    data=excel_fase,
                                    file_name=f"casos_fase_{numero_fase}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"download_fase_{numero_fase}",
                                    use_container_width=True,
                                )

                        if casos_fase:
                            for i in range(0, len(casos_fase), 2):
                                col1, col2 = st.columns(2)
                                pares = [(col1, i)]

                                if i + 1 < len(casos_fase):
                                    pares.append((col2, i + 1))

                                for col, idx in pares:
                                    caso_id, caso = casos_fase[idx]
                                    fase_info = FASES_INFO.get(caso.get("fase", 0), FASES_INFO[0]).copy()

                                    titulo_lista = f"{LABEL_IDENTIFICADOR}: {caso.get('identificador', 'N/A')} | {caso.get('nome_caso', caso.get('nome', 'Sem nome'))}"

                                    with col:
                                        with st.expander(f"{fase_info['icone']} {titulo_lista}", expanded=False):
                                            mostrar_caso_com_moldura(
                                                caso,
                                                caso_id,
                                                banco,
                                                bot,
                                                f"fase_{numero_fase}_{idx}"
                                            )
                        else:
                            st.info("Nenhum caso nesta fase.")

                        st.markdown("---")
                else:
                    st.info(f"📭 Nenhum caso cadastrado para {banco}")

    elif st.session_state.pagina == "🤖 BOT WHATSAPP":

        if not st.session_state.banco_selecionado:
            st.warning("⚠️ Selecione um banco primeiro.")
            return

        banco = st.session_state.banco_selecionado
        st.header("🤖 BOT WHATSAPP - BRADESCO")

        if st.session_state.auto_bot_ativo:
            st_autorefresh(interval=15 * 1000, key="auto_refresh_bot_15s") #alterar o timer do bot#

            agora_dt = datetime.now()
            deve_executar = False

            if st.session_state.ultimo_ciclo_auto_ts is None:
                deve_executar = True
            else:
                diferenca = (agora_dt - st.session_state.ultimo_ciclo_auto_ts).total_seconds()
                if diferenca >= 180:
                    deve_executar = True

            if deve_executar:
                sucesso_auto, logs_auto = executar_rotina_automatica(bot, banco)

                st.session_state.ultimo_ciclo_auto_ts = agora_dt
                st.session_state.ultimo_ciclo_auto = agora_dt.strftime("%d/%m/%Y %H:%M:%S")
                st.session_state.logs_auto_bot = [
                    f"[{st.session_state.ultimo_ciclo_auto}] {log}" for log in logs_auto
                ]

                if sucesso_auto:
                    st.success(f"✅ Rotina automática executada em {st.session_state.ultimo_ciclo_auto}")
                else:
                    st.error(f"❌ Falha na rotina automática em {st.session_state.ultimo_ciclo_auto}")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🚀 Iniciar Edge", use_container_width=True):
                bot.iniciar_edge()

        with col2:
            if st.button("🔐 Verificar Login WhatsApp", use_container_width=True):
                bot.verificar_login()

        with col3:
            label_auto = "⏸️ Parar Automação" if st.session_state.auto_bot_ativo else "▶️ Iniciar Automação"
            if st.button(label_auto, use_container_width=True):
                st.session_state.auto_bot_ativo = not st.session_state.auto_bot_ativo

                if st.session_state.auto_bot_ativo:
                    st.session_state.ultimo_ciclo_auto_ts = None
                    st.session_state.logs_auto_bot = []

                st.rerun()

        col_logs, col_ultimo = st.columns(2)

        with col_logs:
            with st.expander("📄 Logs da automação", expanded=False):
                if st.session_state.logs_auto_bot:
                    for linha in st.session_state.logs_auto_bot:
                        st.write(linha)
                else:
                    st.write("Nenhum log disponível.")

        with col_ultimo:
            if st.session_state.ultimo_ciclo_auto:
                st.info(f"**Último ciclo automático:** {st.session_state.ultimo_ciclo_auto}")
            else:
                st.info("**Último ciclo automático:** Ainda não executado.")

        st.markdown("---")
        st.subheader("📤 Envio inicial dos casos em fase 0")

        casos = bot.carregar_casos()
        if banco in casos and casos[banco]:

            total_fase_0 = sum(
                1 for caso in casos[banco].values()
                if caso.get("fase", 0) == 0
            )
            total_fase_1 = sum(
                1 for caso in casos[banco].values()
                if caso.get("fase", 0) == 1
            )

            st.info(f"Casos na fase 0 aguardando mensagem inicial: {total_fase_0}")
            st.info(f"Casos na fase 1 aguardando resposta: {total_fase_1}")

            col_envio, col_retorno = st.columns(2)

            with col_envio:
                if st.button("📨 Enviar mensagem inicial", type="primary", use_container_width=True):
                    sucesso, mensagem = bot.enviar_mensagem_caso(banco)
                    if sucesso:
                        st.success(mensagem)
                        st.rerun()
                    else:
                        st.error(mensagem)

            with col_retorno:
                if st.button("🔄 Verificar retornos", use_container_width=True):
                    sucesso, mensagem = bot.verificar_retornos(banco)
                    if sucesso:
                        st.success(mensagem)
                        st.rerun()
                    else:
                        st.error(mensagem)
        else:
            st.info("Nenhum caso disponível para envio.")


# =========================
# 11) EXECUÇÃO
# =========================
if __name__ == "__main__":
    main()