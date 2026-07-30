' iLogic Rule: Run Python manifest merge script from Inventor
' Purpose:
' - lets you trigger combine_from_manifest.py from iLogic
' - avoids pasting Python code into an iLogic VB rule

Imports IOPath = System.IO.Path
Imports IOFile = System.IO.File
Imports System.Collections.Generic
Imports System.Diagnostics

Sub Main()
    Dim asmDoc As AssemblyDocument = TryCast(ThisApplication.ActiveDocument, AssemblyDocument)
    If asmDoc Is Nothing Then
        MessageBox.Show("Open the top-level assembly (.iam) before running this rule.", "iLogic")
        Return
    End If

    Dim projectRoot As String = IOPath.GetDirectoryName(asmDoc.FullFileName)

    ' Optional: hard-set the Python merge script path here.
    ' Leave empty to auto-search in common locations.
    Dim scriptPathOverride As String = ""

    Dim repoScriptPath As String = ResolveMergeScriptPath(projectRoot, scriptPathOverride)
    Dim scriptDir As String = ""
    Dim vendorDir As String = ""
    If Not String.IsNullOrEmpty(repoScriptPath) Then
        scriptDir = IOPath.GetDirectoryName(repoScriptPath)
        vendorDir = IOPath.Combine(scriptDir, "_vendor")
    End If

    If String.IsNullOrEmpty(repoScriptPath) Then
        MessageBox.Show(
            "Python merge script not found in any expected location." & vbCrLf & vbCrLf &
            "Checked:" & vbCrLf &
            "- " & IOPath.Combine(projectRoot, "combine_from_manifest.py") & vbCrLf &
            "- " & IOPath.Combine(projectRoot, "scripts", "combine_from_manifest.py") & vbCrLf &
            "- " & IOPath.Combine(projectRoot, "PDF_OUTPUT", "combine_from_manifest.py") & vbCrLf & vbCrLf &
            "Set scriptPathOverride in this rule to the full path if needed.",
            "iLogic"
        )
        Return
    End If

    Dim mergeResult As RunResult = RunPythonMerge(projectRoot, repoScriptPath)

    If mergeResult.ExitCode = 0 Then
        MessageBox.Show("Manifest merge completed successfully." & vbCrLf & mergeResult.StdOut, "iLogic")
        Return
    End If

    If mergeResult.StdErr.Contains("Missing PDF library") Then
        Dim installArgs As String = "-m pip install --upgrade --target """" & vendorDir & """" pypdf"
        Dim installResult As RunResult = RunProcess(projectRoot, "python", installArgs)

        If installResult.ExitCode = 0 Then
            Dim retryResult As RunResult = RunPythonMerge(projectRoot, repoScriptPath)
            If retryResult.ExitCode = 0 Then
                MessageBox.Show(
                    "Manifest merge completed after installing pypdf to local _vendor." & vbCrLf & retryResult.StdOut,
                    "iLogic"
                )
                Return
            End If

            MessageBox.Show(
                "pypdf installed, but merge still failed (exit code " & retryResult.ExitCode.ToString() & ")." & vbCrLf & vbCrLf &
                "STDERR:" & vbCrLf & retryResult.StdErr & vbCrLf & vbCrLf &
                "STDOUT:" & vbCrLf & retryResult.StdOut,
                "iLogic"
            )
            Return
        End If

        MessageBox.Show(
            "Auto-install of pypdf failed (exit code " & installResult.ExitCode.ToString() & ")." & vbCrLf & vbCrLf &
            "Run this manually in the same Python environment:" & vbCrLf &
            "python -m pip install --upgrade --target """" & vendorDir & """" pypdf" & vbCrLf & vbCrLf &
            "INSTALL STDERR:" & vbCrLf & installResult.StdErr & vbCrLf & vbCrLf &
            "INSTALL STDOUT:" & vbCrLf & installResult.StdOut,
            "iLogic"
        )
        Return
    End If

    MessageBox.Show(
        "Manifest merge failed (exit code " & mergeResult.ExitCode.ToString() & ")." & vbCrLf & vbCrLf &
        "STDERR:" & vbCrLf & mergeResult.StdErr & vbCrLf & vbCrLf &
        "STDOUT:" & vbCrLf & mergeResult.StdOut,
        "iLogic"
    )
End Sub

Function RunPythonMerge(projectRoot As String, repoScriptPath As String) As RunResult
    Return RunProcess(projectRoot, "python", """" & repoScriptPath & """")
End Function

Function RunProcess(workingDirectory As String, fileName As String, arguments As String) As RunResult
    Dim psi As New ProcessStartInfo()
    psi.FileName = fileName
    psi.Arguments = arguments
    psi.UseShellExecute = False
    psi.RedirectStandardOutput = True
    psi.RedirectStandardError = True
    psi.CreateNoWindow = True
    psi.WorkingDirectory = workingDirectory

    Dim result As New RunResult()

    Try
        Dim p As Process = Process.Start(psi)
        result.StdOut = p.StandardOutput.ReadToEnd()
        result.StdErr = p.StandardError.ReadToEnd()
        p.WaitForExit()
        result.ExitCode = p.ExitCode
    Catch ex As Exception
        result.ExitCode = -1
        result.StdErr = ex.Message
        result.StdOut = ""
    End Try

    Return result
End Function

Function ResolveMergeScriptPath(projectRoot As String, scriptPathOverride As String) As String
    If Not String.IsNullOrEmpty(scriptPathOverride) AndAlso IOFile.Exists(scriptPathOverride) Then
        Return scriptPathOverride
    End If

    Dim candidates As New List(Of String) From {
        IOPath.Combine(projectRoot, "combine_from_manifest.py"),
        IOPath.Combine(projectRoot, "scripts", "combine_from_manifest.py"),
        IOPath.Combine(projectRoot, "PDF_OUTPUT", "combine_from_manifest.py")
    }

    For Each candidate As String In candidates
        If IOFile.Exists(candidate) Then
            Return candidate
        End If
    Next

    Return ""
End Function

Class RunResult
    Public ExitCode As Integer
    Public StdOut As String
    Public StdErr As String
End Class
