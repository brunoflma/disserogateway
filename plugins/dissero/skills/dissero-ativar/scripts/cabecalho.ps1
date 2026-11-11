# cabecalho.ps1 - headersHelper do canal Dissero no Windows (24/10/2026).
#
# O Claude Code roda este script antes de cada consulta a loja do plugin e de cada download
# (`headersHelper` em extraKnownMarketplaces.dissero.source, Claude Code 2.1.238 ou superior). Ele
# le o token desta maquina no Gerenciador de Credenciais do Windows (credencial generica
# `dissero-canal`, gravada pelo gate de licenca ou pelo ativar_canal) e imprime UM objeto JSON com o
# cabecalho Authorization. O token nunca fica no settings.json.
#
# Sai com erro, sem imprimir nada, quando nao ha credencial ou o formato e inesperado: o Claude Code
# entao nao faz a consulta, e a copia instalada segue como esta.
# Copiado para %USERPROFILE%\.dissero\ (caminho estavel); a fonte e _shared/cabecalho.ps1.
# Como o settings o chama (cofre_maquina.COMANDO_WINDOWS), e como roda numa maquina virgem:
#   powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%USERPROFILE%\.dissero\cabecalho.ps1"
$ErrorActionPreference = 'Stop'
$alvo = if ($env:DSR_COFRE_ALVO) { $env:DSR_COFRE_ALVO } else { 'dissero-canal' }
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace DisseroCofre {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct Credencial {
    public int Flags; public int Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public int CredentialBlobSize; public IntPtr CredentialBlob; public int Persist;
    public int AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName;
  }
  public static class Api {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredReadW(string target, int type, int flags, out IntPtr cred);
    [DllImport("advapi32.dll")]
    public static extern void CredFree(IntPtr cred);
    public static string Ler(string alvo) {
      IntPtr p;
      if (!CredReadW(alvo, 1, 0, out p)) return null;
      try {
        Credencial c = (Credencial)Marshal.PtrToStructure(p, typeof(Credencial));
        return Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2);
      } finally { CredFree(p); }
    }
  }
}
'@
$token = [DisseroCofre.Api]::Ler($alvo)
if (-not $token) { exit 1 }
$token = $token.Trim()
if ($token -notmatch '^[A-Za-z0-9_-]{20,200}$') { exit 1 }
[Console]::Out.Write('{"Authorization":"Bearer ' + $token + '"}')
exit 0
