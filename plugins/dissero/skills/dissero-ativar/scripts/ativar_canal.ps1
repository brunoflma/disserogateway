<#
ativar_canal.ps1 -- liga o canal de atualizacao automatica do plugin Dissero nesta maquina (Windows).

Irmao do ativar_canal.py, para a maquina do comprador: Windows 10/11 com o Windows
PowerShell 5.1 e mais nada (sem Python, sem bash, sem pwsh). Cada linha aqui e compativel com
o 5.1; o pwsh 7 tambem roda. O arquivo fica ASCII puro e sem BOM, porque o 5.1 le arquivo sem
BOM como ANSI.

O que ele faz (desde a 3.0 so pelo LOGIN do conector dissero; nao ha ativacao por chave digitada):
  1. Le o login do conector dissero no store do Claude Code (.credentials.json da pasta de
     configuracao, que respeita CLAUDE_CONFIG_DIR;
     `mcpOAuth`, casado pela `serverUrl` = <origem>/mcp: a mesma regra do gate e do .py) e faz
     `tools/call ativar_maquina` no /mcp com esse bearer -> token POR MAQUINA.
  2. Guarda o token no Gerenciador de Credenciais do Windows (credencial generica dissero-canal,
     a mesma do cofre_maquina.py) e copia o cabecalho.ps1 para %USERPROFILE%\.dissero\. O token
     nunca vai para o settings (24/10/2026; ate a 3.0.0 ia em texto puro no cabecalho). Conferido
     o token no cofre, apaga o cache da licenca do gate (licenca.json na pasta do estado).
  3. Mescla no settings.json a declaracao extraKnownMarketplaces.dissero, com o `headersHelper`
     (o comando que entrega o cabecalho na hora) e `autoUpdate = $true` como IRMAO de `source`
     (dentro de `source` o Claude Code recusa o marketplace inteiro). O resto do arquivo fica.
  4. `claude plugin install dissero@dissero --scope user`, sob a trava de instalacao, e so com o
     Claude Code na versao minima ($CLAUDE_CODE_MINIMO, a mesma CLAUDE_CODE_MINIMO do .py).

Nunca imprime o login nem o token: so o sha256 truncado. Nao toca em managed-settings.json.
Nao eleva. Sem BOM na gravacao: o Node recusa BOM com "Unexpected token". O que so o .py faz
esta no docstring dele.

Uso:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\ativar_canal.ps1
  ... -SemInstalar          grava a declaracao e nao roda o install
  ... -Token <t>            pula o /mcp (reparo e teste)
  ... -Credenciais <arq>    outro store do login (teste)
  ... -Trava <arquivo>      outra trava de instalacao (teste)
  ... -PastaEstado <pasta>  onde vai a marca de pendencia (teste)
Saidas: 0 ok (inclusive instalacao ja em andamento), 1 erro do proprio PowerShell, 3 o canal
recusou (com o texto da recusa; inclusive licenca vencida ou aguardando ativacao, o HTTP 403 da
guarda), 4 canal inacessivel, resposta sem token, ou canal que respondeu sem concluir (o HTTP 503
da guarda, ou erro JSON-RPC com HTTP 200), 5 a gravacao nao conferiu, 6 o install falhou, 8
settings ilegivel (o settings nao foi tocado; com -Token, ou se o arquivo ficou ilegivel durante a
chamada ao canal, a linha 'cofre:' ja saiu e o token desta maquina ja esta no cofre), 9 settings
em uso ou sendo gravado por outro programa (nenhuma configuracao do advogado mudou; se a linha
'cofre:' saiu antes, a licenca ja vale e so a declaracao falta), ou gravado e nao relido (a
declaracao foi gravada e o arquivo estava em uso na releitura; nada foi desfeito), 10 sem login
valido do conector dissero (ausente, vencido ou recusado com 401), 11 Claude Code abaixo da versao
minima, 12 o cofre do sistema nao aceitou o token, ou aceitou e a copia do cabecalho.ps1 falhou
(nada foi gravado no settings), ou, so aqui e com a declaracao ja gravada, o cofre perdeu o token
na conferencia final e nao o guardou de novo, 127 `claude` fora do PATH. De 3 a 12 os codigos sao
os do ativar_canal.py, e as linhas de 3, 4, 8, 9, 11 e 12 sao as dele, sem acento (menos a da
conferencia final do cofre, que so o .ps1 tem). Depois da linha
'cofre:', a declaracao que faltar e gravada pelo gate de licenca na sessao seguinte (a marca de
pendencia, igual a `marcar_pendente` do .py), quando o hook de licenca roda nesta maquina; se a
marca nao pode ser gravada (pasta do estado sem escrita), as linhas das saidas 9 e 12 dizem isso
e mandam rodar de novo, em vez de prometer a sessao seguinte. Caminho com `~` no inicio (inclusive
em CLAUDE_CONFIG_DIR) vale como no .py: a pasta do usuario (USERPROFILE).
#>
param(
    [string]$Maquina = $env:COMPUTERNAME,
    [string]$Origem = 'https://dissero.bfldevlabs.studio',
    [string]$Settings = (Join-Path $(if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }) 'settings.json'),
    [string]$Credenciais = (Join-Path $(if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }) '.credentials.json'),
    [string]$Token,
    [string]$Trava = (Join-Path $HOME '.dissero\instalacao.lock'),
    [string]$PastaEstado = (Join-Path $HOME '.dissero'),
    [switch]$SemInstalar
)
$ErrorActionPreference = 'Stop'
# O TIL (`~`) no inicio de um caminho, como o `expanduser` do Python no Windows (ntpath), que e o
# que o .py e o gate usam para casar a marca de pendencia: `~` sozinho ou seguido de barra vira a
# pasta do usuario (USERPROFILE; sem ela, HOMEDRIVE + HOMEPATH; sem as duas, nada muda) e `~nome`
# vira a pasta irma `nome`, so quando a do usuario termina no nome dele. Sem isto (medido em
# 27/10/2026), CLAUDE_CONFIG_DIR com `~` saia 9 dizendo "em uso" sem ninguem usar o arquivo: o
# Test-Path expande o til pelo provedor e o [IO.File] nao. E a marca gravava
# '<pasta atual>\~\...', que o gate nao casa. O $HOME do PowerShell (5.1 e 7) tambem vem do
# USERPROFILE, e nao de HOME nem de HOMEDRIVE + HOMEPATH (medido em 28/10/2026).
function ExpandirTil([string]$caminho) {
    if (-not $caminho -or -not $caminho.StartsWith('~')) { return $caminho }
    $i = 1
    while ($i -lt $caminho.Length -and '\/'.IndexOf($caminho[$i]) -lt 0) { $i++ }
    if ($null -ne $env:USERPROFILE) { $casa = [string]$env:USERPROFILE }
    elseif ($null -eq $env:HOMEPATH) { return $caminho }
    else { $casa = [string]$env:HOMEDRIVE + [string]$env:HOMEPATH }
    if ($i -ne 1) {
        $nome = $caminho.Substring(1, $i - 1)
        if ($nome -cne $env:USERNAME) {
            if ($env:USERNAME -cne [System.IO.Path]::GetFileName($casa)) { return $caminho }
            $casa = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($casa), $nome)
        }
    }
    return $casa + $caminho.Substring($i)
}
$Settings = ExpandirTil $Settings
$Credenciais = ExpandirTil $Credenciais
$Trava = ExpandirTil $Trava
$PastaEstado = ExpandirTil $PastaEstado
$MERCADO = 'dissero'
$PLUGIN  = "dissero@$MERCADO"
$UA      = 'dissero/1.0'
# A versao minima do Claude Code: a mesma CLAUDE_CODE_MINIMO do ativar_canal.py (o teste confere).
$CLAUDE_CODE_MINIMO = '2.1.295'

# O COFRE (24/10/2026). O token vai ao Gerenciador de Credenciais do Windows, na mesma credencial
# generica que o cofre_maquina.py usa (`dissero-canal`, ou DSR_COFRE_ALVO no teste), em UTF-16,
# que e como o cabecalho.ps1 a le. O settings guarda so o comando abaixo, igual ao
# cofre_maquina.COMANDO_WINDOWS (test_ativar_canal confere a paridade).
$COMANDO_HELPER = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%USERPROFILE%\.dissero\cabecalho.ps1"'
$ALVO_COFRE = if ($env:DSR_COFRE_ALVO) { $env:DSR_COFRE_ALVO } else { 'dissero-canal' }
$PASTA_COFRE = if ($env:DSR_COFRE_PASTA) { $env:DSR_COFRE_PASTA } else { Join-Path $HOME '.dissero' }
function CofreApi {
    if (-not ('DisseroCofreEscrita.Api' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace DisseroCofreEscrita {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct Credencial {
    public int Flags; public int Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public int CredentialBlobSize; public IntPtr CredentialBlob; public int Persist;
    public int AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  public static class Api {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredWriteW(ref Credencial cred, int flags);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredReadW(string target, int type, int flags, out IntPtr cred);
    [DllImport("advapi32.dll")]
    public static extern void CredFree(IntPtr cred);
    public static bool Gravar(string alvo, string token) {
      byte[] blob = System.Text.Encoding.Unicode.GetBytes(token);
      IntPtr p = Marshal.AllocHGlobal(blob.Length);
      try {
        Marshal.Copy(blob, 0, p, blob.Length);
        Credencial c = new Credencial();
        c.Type = 1; c.TargetName = alvo; c.Comment = "Dissero: token de maquina do canal de atualizacao";
        c.CredentialBlobSize = blob.Length; c.CredentialBlob = p; c.Persist = 2; c.UserName = "maquina";
        return CredWriteW(ref c, 0);
      } finally { Marshal.FreeHGlobal(p); }
    }
    public static string Ler(string alvo) {
      IntPtr p;
      if (!CredReadW(alvo, 1, 0, out p)) return null;
      try {
        Credencial c = (Credencial)Marshal.PtrToStructure(p, typeof(Credencial));
        return Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2);
      } finally { CredFree(p); }
    }
    // Grava e confere em laco, como `_win_gravar_conferido` do cofre_maquina.py: a volta em que
    // ficou; -1 se a gravacao foi recusada; 0 se nenhuma volta ficou.
    public static int GravarConferido(string alvo, string token, int voltas, int esperaMs) {
      for (int v = 1; v <= voltas; v++) {
        if (!Gravar(alvo, token)) return -1;
        if (Ler(alvo) != token) continue;
        System.Threading.Thread.Sleep(esperaMs);
        if (Ler(alvo) == token) return v;
      }
      return 0;
    }
  }
}
'@
    }
}
# GRAVAR E CONFERIR EM LACO (28/10/2026, rodada 4), os mesmos VOLTAS_WINDOWS e ESPERA_WINDOWS_S do
# cofre_maquina.py (o teste confere a paridade): sob uso concorrente o Gerenciador de Credenciais
# devolve, e as vezes GUARDA, o valor anterior de uma credencial recem-gravada; a troca aparece ate
# ~400 ms depois, e uma gravacao nova resolve. O motivo, medido, esta no cofre_maquina.py.
$VOLTAS_COFRE = 4
$ESPERA_COFRE_MS = 500
# So no alvo de TESTE a suite encurta a espera (DSR_COFRE_ESPERA_MS); o alvo real nunca a le.
if ($ALVO_COFRE -like 'dissero-canal-teste*' -and $env:DSR_COFRE_ESPERA_MS -match '^\d+$') { $ESPERA_COFRE_MS = [int]$env:DSR_COFRE_ESPERA_MS }
function GravarConferido([string]$tok) {
    try { CofreApi; return [DisseroCofreEscrita.Api]::GravarConferido($ALVO_COFRE, $tok, $VOLTAS_COFRE, $ESPERA_COFRE_MS) }
    catch { return -1 }
}
function GuardarNoCofre([string]$tok) {
    # Grava o token e copia o comando que o le. 'ok'; 'cofre' se o cofre recusou ou nao guardou em
    # nenhuma volta do laco (o settings nao foi tocado); 'copia' se o token ficou no cofre e so a
    # copia do cabecalho.ps1 falhou (o motivo fica em $script:ErroCopia). Com o token no cofre, a
    # marca de pendencia nasce antes da copia.
    if ((GravarConferido $tok) -le 0) { return 'cofre' }
    $script:Marcou = MarcarPendente
    # O cofre conferiu o token novo: o cache da licenca do gate sai (ver ApagarCacheLicenca).
    $script:CacheFora = ApagarCacheLicenca
    try {
        $destino = $PASTA_COFRE
        if (-not (Test-Path -LiteralPath $destino)) { New-Item -ItemType Directory -Path $destino -Force | Out-Null }
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'cabecalho.ps1') -Destination (Join-Path $destino 'cabecalho.ps1') -Force
        return 'ok'
    } catch { $script:ErroCopia = $_.Exception.Message; return 'copia' }
}
# A DECLARACAO PENDENTE: a mesma marca de `marcar_pendente` do ativar_canal.py, no mesmo formato
# (o gate a le pelo campo `settings`, nao pelo nome). Com o token no cofre a licenca vale e a
# ativacao nao roda mais; e a marca que faz o gate de licenca gravar, numa sessao seguinte, a
# declaracao que esta gravacao nao deixar. Falha aqui nao impede a ativacao: devolve $false, e as
# linhas das saidas 9 e 12 trocam a promessa da sessao seguinte pela frase que manda rodar de novo.
function MarcarPendente {
    try {
        $cheio = [System.IO.Path]::GetFullPath($Settings)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $h = (($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($cheio.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 12)
        if (-not (Test-Path -LiteralPath $PastaEstado)) { New-Item -ItemType Directory -Force -Path $PastaEstado | Out-Null }
        $json = ([ordered]@{ settings = $cheio; desde = (AgoraEpoch); motivo = 'ativar_canal.ps1'; gravacoes = 0; falhas = 0 }) | ConvertTo-Json -Compress
        $null = TrocarAtomico (Join-Path $PastaEstado "declaracao-pendente-$h.json") ((New-Object System.Text.UTF8Encoding($false)).GetBytes($json))
        return $true
    } catch { return $false }
}
# O CACHE DA LICENCA: o mesmo `apagar_cache_licenca` do .py (o motivo esta no CACHE_LICENCA de
# la). O gate de licenca guarda em <pasta do estado>\licenca.json a ultima conferencia no servidor
# e, por 24 h, nao volta a ele enquanto o token do cofre tiver a mesma marca; se o cofre perder o
# token novo e voltar ao anterior, que o servidor ja apagou nesta ativacao, o cache o liberaria.
# Conferido o token novo, o cache sai, e o gate confere no servidor na proxima sessao. $true se ele
# nao existe mais (ou nunca existiu); $false se continua la (recusado, ou o nome e uma pasta).
$script:CacheFora = $true
$LINHA_CACHE_NAO_APAGADO = 'licenca: nao foi possivel apagar {0}, o cache da ultima conferencia da licenca. A ativacao vale; o gate de licenca volta a conferir no servidor em ate 24 h.'
function ApagarCacheLicenca {
    $p = Join-Path $PastaEstado 'licenca.json'
    try {
        if (Test-Path -LiteralPath $p -PathType Leaf) { Remove-Item -LiteralPath $p -Force -ErrorAction Stop }
        return (-not (Test-Path -LiteralPath $p))
    } catch { return $false }
}
# As PROMESSAS de que a sessao seguinte completa so sao verdade com a marca gravada. Sem ela, a
# promessa sai e entra a frase SEM_MARCA: `linha_sem_promessa` do .py, com as mesmas frases sem
# acento (o teste confere a paridade).
$script:Marcou = $false
$PROMESSA_PENDENTE = 'Se nao rodar, a proxima sessao do Claude Code grava a declaracao sozinha.'
$PROMESSA_NAO_RELIDO = ', e a proxima sessao do Claude Code confere a declaracao e a grava de novo, se faltar.'
$PROMESSA_AUXILIAR = 'A proxima sessao do Claude Code tenta a copia e a declaracao de novo, sozinha.'
$SEM_MARCA_PENDENTE = "A pendencia tambem nao pode ser anotada em $PastaEstado (a pasta nao aceitou a gravacao), e por isso nenhuma sessao do Claude Code grava a declaracao sozinha: rode este comando de novo."
$SEM_MARCA_NAO_RELIDO = ". A pendencia nao pode ser anotada em $PastaEstado (a pasta nao aceitou a gravacao), e por isso nenhuma sessao do Claude Code confere a declaracao sozinha: feche as outras sessoes do Claude Code e rode este comando de novo; ele confere a declaracao e a grava, se faltar."
$SEM_MARCA_AUXILIAR = "A pendencia tambem nao pode ser anotada em $PastaEstado (a pasta nao aceitou a gravacao), e por isso nenhuma sessao do Claude Code tenta a copia sozinha: corrija a permissao de gravacao dessa pasta e rode este comando de novo."
function SemPromessa([string]$linha, [string]$promessa, [string]$semMarca) {
    if ($script:Marcou) { return $linha }
    return $linha.Replace($promessa, $semMarca)
}
function LerDoCofre {
    try { CofreApi; return [DisseroCofreEscrita.Api]::Ler($ALVO_COFRE) } catch { return $null }
}

function Marca([string]$s) {
    if (-not $s) { return '(ausente)' }
    # SHA256.Create().ComputeHash e do .NET Framework: HashData() nao existe no 5.1.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $h = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($s))
    return (($h | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 12)
}
# GRAVACAO SEGURA, a mesma regra do ativar_canal.py: (1) sem mudanca nao grava; (2) arquivo que
# existe e nao e objeto JSON valido (vazio, truncado) NUNCA e trocado, sai 8; (3) troca atomica,
# por arquivo irmao temporario + File.Replace; (4) compare-and-swap: logo antes de cada troca, com
# a copia e o temporario ja gravados, o arquivo e conferido contra os bytes lidos; se mudou (o
# Claude Code trocando o modelo, por exemplo), a volta recomeca da leitura nova, e se mudou nas
# tres voltas nada e gravado e sai 9; (5) copia settings.json.bak-dsr-<carimbo UTC> antes de
# trocar, redigida por nome de chave, so as 5 mais recentes, e a copia de uma volta que nao trocou
# sai; (6) releitura: se faltar chave de topo do advogado, os bytes anteriores voltam inteiros e
# sai 5; se faltar so a declaracao, outro programa regravou o arquivo por cima da troca, e o
# arquivo dele fica como esta (sai 9); releitura RECUSADA espera como a troca recusada e, esgotado o
# prazo, nada e desfeito (sai 9, `SairNaoRelido`). Sobra o intervalo entre a leitura da
# conferencia e o fim do File.Replace, que sem uma trava respeitada pelo Claude Code nao se fecha:
# medido em 27/10/2026, 10 a 18 ms de mediana e pico de 72 ms (o do .py e ~2 ms), porque cada passo
# aqui passa pelo interpretador do PowerShell.
function Decodificar([byte[]]$bytes) {
    # UTF8Encoding($false, $true): lanca em byte invalido. TrimStart do U+FEFF: le com BOM.
    $t = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($bytes).TrimStart([char]0xFEFF)
    if ([string]::IsNullOrWhiteSpace($t)) { throw 'settings_ilegivel' }
    $o = $t | ConvertFrom-Json
    if ($null -eq $o -or $o -isnot [System.Management.Automation.PSCustomObject]) { throw 'settings_ilegivel' }
    return $o
}
function LerJson([string]$caminho) {
    if (-not (Test-Path -LiteralPath $caminho)) { return $null }
    try { return (Decodificar ([System.IO.File]::ReadAllBytes($caminho))) } catch { return $null }
}
function EFaltando($registro) {
    $e = $registro.Exception
    while ($null -ne $e) {
        if ($e -is [System.IO.FileNotFoundException] -or $e -is [System.IO.DirectoryNotFoundException]) { return $true }
        $e = $e.InnerException
    }
    return $false
}
# A RELEITURA que confere a troca: @{ estado = 'ok' | 'ausente' | 'ilegivel' | 'recusado'; objeto }.
# Leitura RECUSADA (outro processo com o arquivo aberto, sem gravar nada) nao e arquivo ilegivel:
# espera o prazo da troca recusada (40 tentativas, 25 ms de espera entre elas: ~1 s de espera
# pedida, que medida de ponta a ponta deu de 1,3 a 2,8 s sob carga), como o `_conferir` do .py.
# Ler a recusa como ilegivel desfazia uma gravacao boa e dizia ao advogado que configuracoes dele
# tinham sumido.
function LerConferencia([string]$caminho) {
    $ultimo = 'recusado'
    for ($i = 0; $i -lt 40; $i++) {
        if ($i -gt 0) { Start-Sleep -Milliseconds 25 }
        $bytes = $null
        try { $bytes = [System.IO.File]::ReadAllBytes($caminho) }
        catch {
            if (EFaltando $_) { return @{ estado = 'ausente'; objeto = $null } }
            if (ErroDeArquivo $_) { $ultimo = 'recusado'; continue }
            throw
        }
        try { return @{ estado = 'ok'; objeto = (Decodificar $bytes) } } catch { $ultimo = 'ilegivel' }
    }
    return @{ estado = $ultimo; objeto = $null }
}
# O sistema de arquivos recusou ler, copiar ou trocar o settings (outro programa com o arquivo
# aberto, permissao negada): a saida nomeada 9 do ativar_canal.py, e nao um erro cru do
# PowerShell. A excecao do .NET chega embrulhada (MethodInvocationException), por isso a cadeia.
function ErroDeArquivo($registro) {
    $e = $registro.Exception
    while ($null -ne $e) {
        if ($e -is [System.IO.IOException] -or $e -is [System.UnauthorizedAccessException]) { return $true }
        $e = $e.InnerException
    }
    return $false
}
function SairSettingsEmUso {
    Write-Host "ativar_canal: $Settings esta em uso por outro programa neste momento, e por isso nao foi trocado. Feche o Claude Code. Depois rode este comando de novo." -ForegroundColor Red
    exit 9
}
function Serializar($objeto) {
    # -Depth 100: o padrao (2) grava source.headers como a string "System.Object" e o token some;
    # e qualquer teto menor que a profundidade do settings do advogado achataria a parte dele.
    # UTF8Encoding($false): sem BOM. Set-Content -Encoding utf8 grava BOM no 5.1.
    $json = $objeto | ConvertTo-Json -Depth 100
    return (New-Object System.Text.UTF8Encoding($false)).GetBytes($json + "`n")
}
function EscreverNovo([string]$caminho, [byte[]]$bytes) {
    $fs = New-Object System.IO.FileStream($caminho, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try { $fs.Write($bytes, 0, $bytes.Length); $fs.Flush($true) } finally { $fs.Dispose() }
}
$MARCA_MUDOU = 'dsr_settings_mudou'
function AindaE([string]$caminho, [byte[]]$antes) {
    # 'igual' se o arquivo ainda e `antes` ($null = nao existia), 'mudou' se nao, e 'recusado' se a
    # leitura foi recusada agora (outro processo no meio de uma troca): quem chama espera e confere
    # de novo, e nunca le isso como 'igual'.
    if (-not (Test-Path -LiteralPath $caminho)) { if ($null -eq $antes) { return 'igual' } else { return 'mudou' } }
    $agora = $null
    try { $agora = [System.IO.File]::ReadAllBytes($caminho) }
    catch [System.IO.FileNotFoundException] { if ($null -eq $antes) { return 'igual' } else { return 'mudou' } }
    catch { return 'recusado' }
    if ($null -eq $antes) { return 'mudou' }
    if ([Convert]::ToBase64String($agora) -ceq [Convert]::ToBase64String($antes)) { return 'igual' }
    return 'mudou'
}
function TrocarAtomico([string]$caminho, [byte[]]$bytes, [switch]$Cas, [byte[]]$Antes) {
    # [NullString]::Value, e nao $null: o PowerShell passa $null como '' a um parametro string do
    # .NET, e File.Replace recusa backup '' com "The path is empty".
    # Com -Cas, o arquivo e conferido contra -Antes logo antes de CADA troca, com o temporario ja
    # gravado: se mudou, lanca $MARCA_MUDOU sem trocar. Conferencia que nao consegue ler espera
    # como a troca recusada; esgotado o prazo, lanca IOException (saida 9 de quem chama).
    $dir = Split-Path -Parent $caminho
    if (-not $dir) { $dir = '.' }
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $tmp = Join-Path $dir ('.' + (Split-Path -Leaf $caminho) + '.' + [guid]::NewGuid().ToString('N') + '.tmp-dsr')
    try {
        EscreverNovo $tmp $bytes
        for ($i = 0; $i -lt 40; $i++) {
            if ($Cas) {
                $igual = AindaE $caminho $Antes
                if ($igual -eq 'mudou') { throw $MARCA_MUDOU }
                if ($igual -eq 'recusado') {
                    if ($i -eq 39) { throw (New-Object System.IO.IOException "$caminho nao pode ser lido para conferir a troca") }
                    Start-Sleep -Milliseconds 25
                    continue
                }
            }
            try {
                if (Test-Path -LiteralPath $caminho) { [System.IO.File]::Replace($tmp, $caminho, [NullString]::Value) }
                else { [System.IO.File]::Move($tmp, $caminho) }
                return
            } catch {
                # Outro processo com o arquivo aberto: esperar um pouco; desistir sem gravar e
                # melhor que gravar sem atomicidade.
                if ($i -eq 39) { throw }
                Start-Sleep -Milliseconds 25
            }
        }
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    }
}
# A copia NUNCA guarda credencial em texto puro: a mesma redacao do ativar_canal.py, por NOME DE
# CHAVE e so dentro dos dicionarios que guardam credencial (`headers` de marketplace, `env` do
# advogado). Quando nada ha a redigir, os bytes originais vao verbatim.
$MARCADOR_OMITIDO = '<omitido pelo plugin>'
$NOMES_SIGILOSOS = @('token', 'secret', 'key', 'password', 'passphrase', 'auth', 'senha')
$DICIONARIOS_SIGILOSOS = @('headers', 'env')

function ESigiloso([string]$nome) {
    $n = $nome.ToLowerInvariant()
    foreach ($s in $NOMES_SIGILOSOS) { if ($n.Contains($s)) { return $true } }
    return $false
}
function RedigirParaCopia($o, [string]$dono) {
    if ($o -is [System.Management.Automation.PSCustomObject]) {
        $saida = [pscustomobject]@{}
        foreach ($prop in $o.PSObject.Properties) {
            $valor = $null
            if (($DICIONARIOS_SIGILOSOS -contains $dono) -and ($prop.Value -is [string]) -and (ESigiloso $prop.Name)) {
                $valor = $MARCADOR_OMITIDO
            } else {
                $valor = RedigirParaCopia $prop.Value ($prop.Name.ToLowerInvariant())
            }
            $saida | Add-Member -NotePropertyName $prop.Name -NotePropertyValue $valor -Force
        }
        return $saida
    }
    if ($o -is [System.Collections.IEnumerable] -and $o -isnot [string]) {
        # A virgula impede o PowerShell de desenrolar o array no pipeline e achatar a estrutura.
        return , @($o | ForEach-Object { RedigirParaCopia $_ $dono })
    }
    return $o
}

function GuardarCopia([string]$caminho, [byte[]]$bytes, $objeto) {
    if ($null -ne $objeto) {
        $redigido = RedigirParaCopia $objeto ''
        $bytesRedigidos = Serializar $redigido
        if ([System.Text.Encoding]::UTF8.GetString($bytesRedigidos) -ne [System.Text.Encoding]::UTF8.GetString((Serializar $objeto))) {
            $bytes = $bytesRedigidos
        }
    }
    $agora = [DateTime]::UtcNow  # UTC: a volta do horario de verao nao inverte a ordem das copias
    $base = $caminho + '.bak-dsr-' + $agora.ToString('yyyyMMddTHHmmss') + $agora.ToString('ffffff')
    $destino = $base; $n = 0
    while (Test-Path -LiteralPath $destino) { $n++; $destino = "$base-$n" }
    EscreverNovo $destino $bytes
    return $destino
}
function PodarCopias([string]$caminho) {
    # So as 5 mais recentes. Roda depois da troca: uma volta que desistiu apaga a propria copia, e
    # podar antes dela custaria a mais antiga a toa.
    $lista = @(Get-ChildItem -LiteralPath (Split-Path -Parent $caminho) -Filter ((Split-Path -Leaf $caminho) + '.bak-dsr-*') | Sort-Object Name)
    if ($lista.Count -gt 5) { $lista[0..($lista.Count - 6)] | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue } }
}

# TRAVA DE INSTALACAO: a mesma do ativar_canal.py e do gate (mesmo arquivo, mesmo JSON `pid` e
# `em` em segundos desde 1970, mesmas regras de trava velha), para dois `claude plugin` nunca
# rodarem juntos sobre o mesmo settings.json.
$TRAVA_IDADE_S = 900

function AgoraEpoch {
    # (New-Object DateTime 1970,1,1), e nao [DateTime]'1970-01-01T00:00:00Z': a string com Z vira
    # hora LOCAL, e a diferenca para UtcNow sai deslocada pelo fuso (a trava viva pareceria velha).
    return ([DateTime]::UtcNow - (New-Object DateTime 1970, 1, 1)).TotalSeconds
}
function ProcessoVivo([int]$processo) {
    if ($processo -le 0) { return $false }
    try { $null = Get-Process -Id $processo -ErrorAction Stop; return $true } catch { return $false }
}
function LerTrava([string]$caminho) {
    try { $d = (Get-Content -LiteralPath $caminho -Raw -ErrorAction Stop) | ConvertFrom-Json } catch { return $null }
    if ($null -eq $d -or -not $d.PSObject.Properties['pid']) { return $null }
    return $d
}
function TravaVelha([string]$caminho, $info, [double]$idadeMax) {
    if ($null -eq $info) {
        # Ilegivel: pode ser alguem no meio de cria-la. So e lixo quando o arquivo ja e velho.
        try { return ((([DateTime]::UtcNow - (Get-Item -LiteralPath $caminho).LastWriteTimeUtc).TotalSeconds) -gt $idadeMax) }
        catch { return $true }
    }
    $em = 0.0
    try { $em = [double]$info.em } catch { $em = 0.0 }
    if (((AgoraEpoch) - $em) -gt $idadeMax) { return $true }
    return (-not (ProcessoVivo ([int]$info.pid)))
}
function AdquirirTrava([string]$caminho, [double]$idadeMax) {
    $dir = Split-Path -Parent $caminho
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    for ($i = 0; $i -lt 3; $i++) {
        $fs = $null
        try { $fs = New-Object System.IO.FileStream($caminho, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None) } catch { $fs = $null }
        if ($null -ne $fs) {
            try {
                $txt = (@{ pid = $PID; em = (AgoraEpoch) } | ConvertTo-Json -Compress)
                $b = (New-Object System.Text.UTF8Encoding($false)).GetBytes($txt)
                $fs.Write($b, 0, $b.Length); $fs.Flush($true)
            } finally { $fs.Dispose() }
            return $true
        }
        $info = LerTrava $caminho
        if (-not (TravaVelha $caminho $info $idadeMax)) { return $false }
        # Trava velha sai do caminho por RENOMEACAO, e so e descartada se o renomeado for a MESMA
        # que foi julgada velha -- senao outro processo acabou de toma-la, e ela volta ao lugar.
        $lixo = "$caminho.velha-$PID-$([DateTime]::UtcNow.Ticks)"
        try { [System.IO.File]::Move($caminho, $lixo) } catch { return $false }
        $mesma = LerTrava $lixo
        $igual = ($null -eq $info -and $null -eq $mesma) -or
                 ($null -ne $info -and $null -ne $mesma -and [string]$mesma.pid -eq [string]$info.pid -and [string]$mesma.em -eq [string]$info.em)
        if (-not $igual) {
            try { [System.IO.File]::Move($lixo, $caminho) } catch {}
            return $false
        }
        Remove-Item -LiteralPath $lixo -Force -ErrorAction SilentlyContinue
    }
    return $false
}
function LiberarTrava([string]$caminho) {
    $info = LerTrava $caminho
    if ($null -ne $info -and [string]$info.pid -eq [string]$PID) {
        Remove-Item -LiteralPath $caminho -Force -ErrorAction SilentlyContinue
    }
}

# 1. O LOGIN do conector dissero: a mesma regra de `ler_login` do .py e do gate. Casa pela URL do
# servidor, nunca pelo nome; entrada sem accessToken e "descoberto, nao autenticado"; vencida e
# expirada. O token nunca sai daqui para a tela.
function LerLogin([string]$caminho, [string]$origem) {
    $alvo = "$($origem.TrimEnd('/'))/mcp"
    $d = LerJson $caminho
    $agoraMs = ([DateTime]::UtcNow - (New-Object DateTime 1970, 1, 1)).TotalMilliseconds
    $melhor = ''; $vencido = $false
    if ($null -ne $d -and $d.PSObject.Properties['mcpOAuth'] -and $d.mcpOAuth -is [System.Management.Automation.PSCustomObject]) {
        foreach ($p in $d.mcpOAuth.PSObject.Properties) {
            $e = $p.Value
            if ($e -isnot [System.Management.Automation.PSCustomObject]) { continue }
            # -cne: comparacao EXATA, como o .py (o -ne do PowerShell ignora a caixa).
            if (([string]$e.serverUrl).TrimEnd('/') -cne $alvo) { continue }
            $tok = ([string]$e.accessToken).Trim()
            if (-not $tok) { continue }
            $exp = $e.expiresAt
            $numero = ($exp -is [int]) -or ($exp -is [long]) -or ($exp -is [double]) -or ($exp -is [decimal])
            if ($numero -and ([double]$exp -le $agoraMs)) { $vencido = $true; continue }
            $melhor = $tok
        }
    }
    if ($melhor) { return @{ situacao = 'valido'; token = $melhor } }
    if ($vencido) { return @{ situacao = 'expirado'; token = '' } }
    return @{ situacao = 'ausente'; token = '' }
}

# A frase de `error.message` no corpo JSON-RPC de uma resposta HTTP de erro, ou ''. Corpo que nao
# e JSON-RPC (a pagina de erro da borda, por exemplo) da ''. Nunca lanca. A mesma regra de
# `_mensagem_jsonrpc` do .py e do gate. A GUARDA DE LICENCA do /mcp (protegerMcp no Worker) recusa
# licenca vencida ou aguardando ativacao com HTTP 403 e a frase em JSON-RPC, e responde 503 na
# mesma forma quando nao consegue conferir (forma medida em 22/10/2026, no docstring do .py).
# No 5.1 o corpo vem do fluxo da resposta, lido do inicio em UTF-8 (o Worker manda
# `application/json` sem charset); no pwsh 7, e no 5.1 quando o fluxo nao se rele, de ErrorDetails.
function MensagemJsonRpc($registro) {
    $texto = ''
    try {
        $r = $registro.Exception.Response
        if ($null -ne $r -and $r -is [System.Net.HttpWebResponse]) {
            $fluxo = $r.GetResponseStream()
            if ($fluxo.CanSeek) { $fluxo.Position = 0 }
            $texto = (New-Object System.IO.StreamReader($fluxo, [System.Text.Encoding]::UTF8)).ReadToEnd()
        }
    } catch { $texto = '' }
    if (-not $texto) {
        try { if ($null -ne $registro.ErrorDetails) { $texto = [string]$registro.ErrorDetails.Message } } catch { $texto = '' }
    }
    if (-not $texto) { return '' }
    try {
        $j = $texto | ConvertFrom-Json
        if ($null -ne $j -and $j.PSObject.Properties['error'] -and $null -ne $j.error -and $j.error.PSObject.Properties['message']) {
            $m = ([string]$j.error.message).Trim()
            if ($m.Length -gt 300) { $m = $m.Substring(0, 300) }
            return $m
        }
    } catch { }
    return ''
}

# `JSON-RPC <code>: <message>` de um `error` JSON-RPC; sem codigo inteiro ou sem frase, a parte que
# falta sai. A mesma regra de `_descrever_erro_jsonrpc` do .py.
function DescreverErroJsonRpc($erro) {
    $texto = 'JSON-RPC'
    $c = $null; $m = ''
    try { if ($null -ne $erro -and $erro.PSObject.Properties['code']) { $c = $erro.code } } catch { $c = $null }
    try { if ($null -ne $erro -and $erro.PSObject.Properties['message']) { $m = ([string]$erro.message).Trim() } } catch { $m = '' }
    if ($c -is [int] -or $c -is [long]) { $texto += " $c" }
    if ($m.Length -gt 300) { $m = $m.Substring(0, 300) }
    if ($m) { $texto += ": $m" }
    return $texto
}

# O canal RESPONDEU sem concluir a ativacao (o 503 da guarda, ou erro JSON-RPC com HTTP 200): falha
# do lado do servidor, e nao da internet nem recusa da licenca. A linha e a do .py (CanalNaoConcluiu).
function SairCanalNaoConcluiu([string]$detalhe) {
    Write-Host "ativar_canal: o canal respondeu, mas nao concluiu a ativacao ($detalhe). A falha e do lado do servidor, e nao da internet: rode este comando de novo mais tarde; se repetir, fale com a Dissero." -ForegroundColor Red
    exit 4
}

if (-not $Token) {
    $login = LerLogin $Credenciais $Origem
    if ($login.situacao -eq 'ausente') {
        Write-Host 'ativar_canal: nao ha login do conector dissero neste computador. Digite /mcp, escolha dissero e autentique com o e-mail liberado pela banca. Depois rode este comando de novo.' -ForegroundColor Red
        exit 10
    }
    if ($login.situacao -eq 'expirado') {
        Write-Host 'ativar_canal: o login do conector dissero neste computador expirou. Digite /mcp, escolha dissero e clique em Reconectar. Depois rode este comando de novo.' -ForegroundColor Red
        exit 10
    }
    # A ordem do gate e do .py: o settings e conferido ANTES de ir ao canal, porque ativar sem
    # conseguir gravar gasta uma vaga de maquina a toa.
    if (Test-Path -LiteralPath $Settings) {
        $previa = $null
        try { $previa = [System.IO.File]::ReadAllBytes($Settings) } catch { if (ErroDeArquivo $_) { SairSettingsEmUso }; throw }
        try { $null = Decodificar $previa } catch {
            Write-Host "ativar_canal: $Settings existe mas nao e um JSON valido, e por isso nao foi substituido (troca-lo apagaria as suas configuracoes). Corrija o arquivo e rode de novo." -ForegroundColor Red
            exit 8
        }
    }
    $corpo = @{ jsonrpc = '2.0'; id = 1; method = 'tools/call'
                params = @{ name = 'ativar_maquina'; arguments = @{ maquina = ([string]$Maquina).Trim() } } } | ConvertTo-Json -Depth 10 -Compress
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$($Origem.TrimEnd('/'))/mcp" -UserAgent $UA `
            -Headers @{ Authorization = "Bearer $($login.token)"; Accept = 'application/json, text/event-stream' } `
            -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($corpo)) -TimeoutSec 30
    } catch {
        $codigo = 0
        try { $codigo = [int]$_.Exception.Response.StatusCode } catch { $codigo = 0 }
        if ($codigo -eq 401) {
            Write-Host 'ativar_canal: o canal nao aceitou o login do conector dissero (HTTP 401). Digite /mcp, escolha dissero e clique em Reconectar. Depois rode este comando de novo.' -ForegroundColor Red
            exit 10
        }
        # 403 com a frase da guarda de licenca e RECUSA (saida 3), como no .py; o 503 dela continua
        # saida 4, com a frase, na linha do canal que respondeu sem concluir (falha do servidor, nao
        # da rede); 403 sem JSON-RPC (pagina da borda) continua saida 4, sem falar com o canal.
        $frase = ''
        if ($codigo -eq 403 -or $codigo -eq 503) { $frase = MensagemJsonRpc $_ }
        if ($codigo -eq 403 -and $frase) {
            Write-Host "ativar_canal: o canal recusou a ativacao: $frase" -ForegroundColor Red
            exit 3
        }
        if ($codigo -gt 0 -and $frase) { SairCanalNaoConcluiu "HTTP ${codigo}: $frase" }
        if ($codigo -gt 0) { Write-Host "ativar_canal: nao foi possivel falar com o canal (HTTP $codigo)." -ForegroundColor Red }
        else { Write-Host "ativar_canal: nao foi possivel falar com o canal ($($_.Exception.GetType().Name))." -ForegroundColor Red }
        exit 4
    }
    # Erro JSON-RPC com HTTP 200 (ferramenta que o servidor nao conhece, forma medida em 22/10/2026,
    # no docstring do .py): o canal respondeu sem executar o pedido. Nao e recusa da licenca (o gate
    # o chama de indisponivel): saida 4, na mesma linha do 503 da guarda, como no .py.
    if ($null -ne $resp -and $resp.PSObject.Properties['error'] -and $null -ne $resp.error) {
        SairCanalNaoConcluiu (DescreverErroJsonRpc $resp.error)
    }
    $res = $null
    if ($null -ne $resp -and $resp.PSObject.Properties['result']) { $res = $resp.result }
    $meta = $null
    if ($null -ne $res -and $res.PSObject.Properties['_meta']) { $meta = $res._meta }
    if ($null -eq $res -or $res.isError -eq $true -or $null -eq $meta -or -not $meta.token) {
        $texto = ''
        if ($null -ne $res -and $res.PSObject.Properties['content']) {
            $texto = ((@($res.content) | Where-Object { $null -ne $_ -and $_.PSObject.Properties['text'] } | ForEach-Object { [string]$_.text }) -join ' ').Trim()
        }
        if (-not $texto) { $texto = 'o canal nao emitiu o token desta maquina' }
        Write-Host "ativar_canal: o canal recusou a ativacao: $texto" -ForegroundColor Red
        exit 3
    }
    $Token = [string]$meta.token
    $usadas = '?'; $permitidas = '?'
    if ($meta.PSObject.Properties['maquinas'] -and $null -ne $meta.maquinas) { $usadas = $meta.maquinas.usadas; $permitidas = $meta.maquinas.permitidas }
    Write-Host "canal: login aceito para o tenant $($meta.tenant) ($usadas/$permitidas maquina(s)); token $(Marca $Token)"
}

# 2. Mescla, nunca sobrescreve: o settings de usuario e o arquivo mais povoado da maquina.
# O token vai ao COFRE antes de qualquer escrita no settings: sem cofre, nada se grava. E vai ANTES
# da leitura do settings, para o intervalo entre ler e trocar nao incluir o Add-Type do cofre.
$cofre = GuardarNoCofre $Token
if ($cofre -eq 'cofre') {
    Write-Host 'ativar_canal: o cofre do sistema nao aceitou o token desta maquina. Nada foi gravado no settings; nao siga.' -ForegroundColor Red
    exit 12
}
Write-Host "cofre: token $(Marca $Token) guardado no Gerenciador de Credenciais do Windows"
if (-not $script:CacheFora) {
    Write-Host ($LINHA_CACHE_NAO_APAGADO -f (Join-Path $PastaEstado 'licenca.json')) -ForegroundColor Yellow
}
if ($cofre -eq 'copia') {
    # O cofre ACEITOU: dizer que ele recusou mandaria investigar o lugar errado. A linha e a do .py.
    Write-Host (SemPromessa "ativar_canal: o token desta maquina ficou no cofre, mas nao foi possivel copiar o comando que o le para ~/.dissero ($script:ErroCopia). Nada foi gravado no settings; nao siga. A proxima sessao do Claude Code tenta a copia e a declaracao de novo, sozinha." $PROMESSA_AUXILIAR $SEM_MARCA_AUXILIAR) -ForegroundColor Red
    exit 12
}
$entrada = [pscustomobject]@{
    source     = [pscustomobject]@{
        source        = 'url'
        url           = "$($Origem.TrimEnd('/'))/marketplace.json"
        headersHelper = $COMANDO_HELPER
    }
    autoUpdate = $true
}
function SairDeclaracaoPendente {
    # Depois do cofre: a declaracao nao ficou e nada do advogado mudou (o sistema recusou ler ou
    # trocar, o arquivo mudou em todas as voltas, ou outro programa o regravou logo depois da
    # troca). A licenca vale e so a declaracao falta. A linha e a LINHA_DECLARACAO_PENDENTE do .py.
    Write-Host (SemPromessa "ativar_canal: $Settings esta em uso ou sendo gravado por outro programa neste momento, e por isso a declaracao do canal nao ficou. Nenhuma configuracao sua foi alterada. O token desta maquina ja esta no cofre: a licenca vale, e so a declaracao falta. Feche as outras sessoes do Claude Code. Depois rode este comando de novo. Se nao rodar, a proxima sessao do Claude Code grava a declaracao sozinha." $PROMESSA_PENDENTE $SEM_MARCA_PENDENTE) -ForegroundColor Red
    exit 9
}
function SairNaoRelido {
    # A troca aconteceu e a releitura foi recusada durante todo o prazo: nada e desfeito. A linha e
    # a LINHA_NAO_RELIDO do .py.
    Write-Host (SemPromessa "ativar_canal: a declaracao do canal foi gravada em $Settings, mas outro programa manteve o arquivo aberto logo depois, e ele nao pode ser relido para conferir. Nada foi desfeito. O token desta maquina ja esta no cofre: a licenca vale, e a proxima sessao do Claude Code confere a declaracao e a grava de novo, se faltar." $PROMESSA_NAO_RELIDO $SEM_MARCA_NAO_RELIDO) -ForegroundColor Red
    exit 9
}
$VOLTAS_CAS = 3
$feito = ''
for ($volta = 0; $volta -lt $VOLTAS_CAS; $volta++) {
    $bruto = $null
    $s = $null
    if (Test-Path -LiteralPath $Settings) {
        try { $bruto = [System.IO.File]::ReadAllBytes($Settings) } catch { if (ErroDeArquivo $_) { SairDeclaracaoPendente }; throw }
        try { $s = Decodificar $bruto } catch {
            Write-Host "ativar_canal: $Settings existe mas nao e um JSON valido, e por isso nao foi substituido (troca-lo apagaria as suas configuracoes). Corrija o arquivo e rode de novo." -ForegroundColor Red
            exit 8
        }
    }
    $existia = $null -ne $s
    if (-not $existia) { $s = [pscustomobject]@{} }
    $chavesAntes = @($s.PSObject.Properties | ForEach-Object { $_.Name })
    $serialAntes = if ($existia) { [System.Text.Encoding]::UTF8.GetString((Serializar $s)) } else { $null }
    if (-not $s.PSObject.Properties['extraKnownMarketplaces'] -or $null -eq $s.extraKnownMarketplaces) {
        $s | Add-Member -NotePropertyName extraKnownMarketplaces -NotePropertyValue ([pscustomobject]@{}) -Force
    }
    $s.extraKnownMarketplaces | Add-Member -NotePropertyName $MERCADO -NotePropertyValue $entrada -Force
    $novoBytes = Serializar $s
    $copia = $null
    if ($existia -and ([System.Text.Encoding]::UTF8.GetString($novoBytes) -eq $serialAntes)) { $feito = 'nada'; break }
    try {
        if ($existia) {
            # Decodificar de novo: `$s` ja foi mutado com a declaracao NOVA, e a copia e do anterior.
            $copia = GuardarCopia $Settings $bruto (Decodificar $bruto)
            Write-Host "settings: copia do arquivo anterior em $copia"
        }
        # COMPARE-AND-SWAP: se o arquivo mudou desde a leitura, `$novoBytes` foi calculado sobre o
        # que ja nao existe, e grava-lo apagaria a escrita do outro programa.
        TrocarAtomico $Settings $novoBytes -Cas -Antes $bruto
        $feito = 'gravado'
        break
    } catch {
        # A troca nao aconteceu: a copia desta volta guarda o que o arquivo ainda e, e sai.
        if ($copia) { Remove-Item -LiteralPath $copia -Force -ErrorAction SilentlyContinue }
        if ($_.Exception.Message -eq $MARCA_MUDOU) {
            Write-Host 'settings: o arquivo mudou durante a gravacao; a gravacao recomeca da leitura nova'
            continue
        }
        if (ErroDeArquivo $_) { SairDeclaracaoPendente }
        throw
    }
}
# Mudou em todas as voltas: o outro programa esta gravando agora, e nada foi trocado.
if (-not $feito) { SairDeclaracaoPendente }
$conf = $null
if ($feito -eq 'nada') {
    Write-Host "settings: a declaracao $MERCADO ja estava gravada; nada a fazer"
    # Nada foi gravado: a leitura desta volta ja achou a declaracao, e e ela que se confere.
    $conf = $s
} else {
    PodarCopias $Settings
    $rel = LerConferencia $Settings
    if ($rel.estado -eq 'recusado') { SairNaoRelido }
    $faltam = @()
    if ($rel.estado -eq 'ilegivel') { $faltam = @('(arquivo ilegivel na releitura)') }
    else {
        $lido = $rel.objeto
        if ($null -eq $lido) { $lido = [pscustomobject]@{} }
        $faltam = @($chavesAntes | Where-Object { -not $lido.PSObject.Properties[$_] })
    }
    if ($faltam.Count -gt 0) {
        # Ilegivel, ou uma chave do advogado sumiu: volta o anterior a partir dos bytes lidos, nao
        # da copia, que esta redigida. O que outro programa gravou nesse intervalo se perde junto.
        $desfecho = 'nao havia arquivo antes, e nada foi restaurado'
        if ($copia) {
            try {
                TrocarAtomico $Settings $bruto
                $desfecho = 'o arquivo anterior foi restaurado inteiro, e o que outro programa gravou nesse intervalo se perdeu junto'
            } catch {
                $desfecho = 'o sistema de arquivos recusou a restauracao, e o arquivo ficou como esta: confira as suas configuracoes nele'
            }
        }
        Write-Host "ativar_canal: a gravacao nao conferiu na releitura (faltam: $($faltam -join ', ')); $desfecho; nao siga." -ForegroundColor Red
        exit 5
    }
    $rel2 = LerConferencia $Settings
    if ($rel2.estado -eq 'recusado') { SairNaoRelido }
    $conf = $rel2.objeto
}

$decl = $null
if ($conf -and $conf.PSObject.Properties['extraKnownMarketplaces'] -and $null -ne $conf.extraKnownMarketplaces -and
    $conf.extraKnownMarketplaces.PSObject.Properties[$MERCADO]) { $decl = $conf.extraKnownMarketplaces.$MERCADO }
if ($null -eq $decl -or $decl.source.headersHelper -ne $COMANDO_HELPER) {
    # Nenhuma chave do advogado sumiu (conferido acima) e a declaracao nao esta la: outro programa
    # regravou o arquivo logo depois da troca. O arquivo dele fica como esta; restaurar o anterior
    # apagaria justamente essa escrita.
    SairDeclaracaoPendente
}
$okTok  = -not $decl.source.PSObject.Properties['headers']
$okAuto = $decl.autoUpdate -eq $true
if (-not ($okTok -and $okAuto)) {
    $desfecho = ''
    if ($copia) {
        try { TrocarAtomico $Settings $bruto; $desfecho = ' O arquivo anterior foi restaurado inteiro.' }
        catch { $desfecho = ' O sistema de arquivos recusou a restauracao, e o arquivo ficou como esta.' }
    }
    Write-Host "ativar_canal: a declaracao nao sobreviveu a gravacao.$desfecho Por isso, nao siga." -ForegroundColor Red
    exit 5
}
# O COFRE DE NOVO, ~1 s depois da gravacao (28/10/2026). A declaracao conferiu; token que nao esta
# no cofre e o cofre que perdeu a gravacao (ver GRAVAR E CONFERIR EM LACO), e nao a declaracao:
# desfazer o settings apagaria uma declaracao certa. O token vai ao cofre de novo pelo mesmo laco.
if ((Marca (LerDoCofre)) -ne (Marca $Token)) {
    if ((GravarConferido $Token) -le 0) {
        Write-Host "ativar_canal: a declaracao do canal ficou gravada em $Settings, mas o cofre do sistema perdeu o token desta maquina depois de aceita-lo, e nao o guardou de novo. Rode este comando de novo, uma vez; nao siga." -ForegroundColor Red
        exit 12
    }
    Write-Host "cofre: o token $(Marca $Token) tinha sumido do cofre depois da gravacao e foi gravado de novo"
}
Write-Host "settings: declaracao $MERCADO gravada em $Settings (headersHelper, autoUpdate: true; sem token)"

# O REGISTRO de lojas do Claude Code guarda uma copia da fonte antiga, com o token; sem po-lo em
# dia, o Claude Code ignora a loja e o plugin nao carrega. So a `source` da entrada do canal muda,
# sob a trava de instalacao. A mesma regra de `reconciliar_registro` do ativar_canal.py; o registro
# sai da pasta do settings, para um settings de teste nunca levar a trocar o registro real.
$Registro = Join-Path (Split-Path -Parent $Settings) 'plugins\known_marketplaces.json'
$reg = LerJson $Registro
if ($reg -and $reg.PSObject.Properties[$MERCADO] -and
    (($reg.$MERCADO.source | ConvertTo-Json -Depth 20 -Compress) -ne ($entrada.source | ConvertTo-Json -Depth 20 -Compress))) {
    if (AdquirirTrava $Trava $TRAVA_IDADE_S) {
        try {
            $reg = LerJson $Registro
            $reg.$MERCADO | Add-Member -NotePropertyName source -NotePropertyValue $entrada.source -Force
            TrocarAtomico $Registro (Serializar $reg)
            Write-Host "registro: a loja $MERCADO do Claude Code passou a usar o headersHelper (o token saiu de $Registro)"
        } catch {
            Write-Host "registro: a loja $MERCADO do Claude Code nao foi posta em dia agora; o gate de licenca tenta de novo na proxima sessao." -ForegroundColor Yellow
        } finally { LiberarTrava $Trava }
    } else {
        Write-Host "registro: a loja $MERCADO do Claude Code nao foi posta em dia agora (outra instalacao em andamento); o gate de licenca tenta de novo na proxima sessao." -ForegroundColor Yellow
    }
}

if ($SemInstalar) { Write-Host 'instalacao pulada (-SemInstalar).'; exit 0 }

# 3. Instala uma vez, no escopo de usuario. Nada eleva.
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Write-Host 'ativar_canal: o comando `claude` nao esta no PATH. Instale o Claude Code e rode de novo.' -ForegroundColor Red
    exit 127
}
if (-not (AdquirirTrava $Trava $TRAVA_IDADE_S)) {
    # A declaracao ja esta gravada; quem detem a trava termina a instalacao sozinho. Rodar um
    # segundo `claude` agora seria exatamente a corrida que esta trava existe para evitar.
    Write-Host 'plugin: outra instalacao do plugin Dissero ja esta em andamento neste computador; ela conclui sozinha e a copia entra em vigor na proxima sessao.'
    exit 0
}
$rcInstall = 1
$versaoClaude = $null
$claudeAntigo = $false
try {
    # A versao minima do Claude Code, SOB A TRAVA e antes do install, como no .py: o --version leva
    # segundos, e medido fora da trava deixaria a segunda sessao instalar de novo. Versao que nao se
    # le nao impede (nao medir nunca vira recusa), como em `abaixo_do_minimo` do .py.
    try {
        $saidaVersao = (& $claude.Source --version 2>&1 | Out-String)
        if ($saidaVersao -match '(\d+)\.(\d+)\.(\d+)') { $versaoClaude = $Matches[0] }
    } catch { $versaoClaude = $null }
    if ($versaoClaude -and (([version]$versaoClaude) -lt ([version]$CLAUDE_CODE_MINIMO))) {
        $claudeAntigo = $true
    } else {
        & $claude.Source plugin install $PLUGIN --scope user
        $rcInstall = $LASTEXITCODE
    }
} finally {
    LiberarTrava $Trava
}
if ($claudeAntigo) {
    Write-Host "ativar_canal: o Claude Code desta maquina esta na versao $versaoClaude, e o plugin Dissero exige a $CLAUDE_CODE_MINIMO ou superior. Atualize o Claude Code (no terminal, ``claude update``) e rode este comando de novo. A declaracao ja ficou gravada; so a instalacao falta." -ForegroundColor Red
    exit 11
}
if ($rcInstall -ne 0) {
    Write-Host "ativar_canal: claude plugin install falhou ($rcInstall)." -ForegroundColor Red
    exit 6
}
Write-Host "plugin: $PLUGIN instalado no escopo de usuario. A partir da proxima sessao, a atualizacao e automatica."
exit 0
