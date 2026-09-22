'========================================
' iLogic Rule: Batch Export Open Drawings to PDF and Close
' Option 1: Manual trigger after users finish edits
'
' PDF filenames use the referenced part/subassembly model iProperties:
' Project -> Part Number
' Project -> Description
' Project -> Revision Number
'
' Existing PDFs with the current date and the same name are overwritten.
'========================================

Sub Main()
    Dim desktopPath As String = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
    Dim outputFolder As String = desktopPath & "\Inventor_PDF_Output"

    If Not System.IO.Directory.Exists(outputFolder) Then
        System.IO.Directory.CreateDirectory(outputFolder)
    End If

    Dim exportedCount As Integer = 0
    Dim overwrittenCount As Integer = 0
    Dim failedCount As Integer = 0
    Dim noReferenceCount As Integer = 0
    Dim noRevisionCount As Integer = 0

    Dim exportedFiles As New System.Text.StringBuilder()
    Dim noReferenceFiles As New System.Text.StringBuilder()
    Dim noRevisionFiles As New System.Text.StringBuilder()
    Dim failedFiles As New System.Text.StringBuilder()

    Dim PDFAddIn As ApplicationAddIn
    PDFAddIn = ThisApplication.ApplicationAddIns.ItemById("{0AC6FD96-2F4D-42CE-8BE0-8AEA580399E4}")

    ' Snapshot drawings first because the loop closes each drawing.
    Dim drawingsToProcess As New System.Collections.ArrayList()
    For Each openDoc As Document In ThisApplication.Documents
        Try
            If openDoc.DocumentType = kDrawingDocumentObject Then
                drawingsToProcess.Add(openDoc)
            End If
        Catch
            ' Ignore inaccessible document handles during collection build.
        End Try
    Next

    For Each drawingObj As Object In drawingsToProcess
        Dim drawingDoc As DrawingDocument = CType(drawingObj, DrawingDocument)

        Try
            Dim referenceSelectionDetails As String = ""
            Dim referencedModel As Document = GetBestReferencedModelFromDrawing(drawingDoc, referenceSelectionDetails)
            Dim outputPath As String

            If referencedModel Is Nothing Then
                noReferenceCount += 1
                Dim drawingFileNameOnly As String = CleanFileName(System.IO.Path.GetFileNameWithoutExtension(drawingDoc.DisplayName))
                outputPath = System.IO.Path.Combine(outputFolder, drawingFileNameOnly & ".pdf")
                noReferenceFiles.AppendLine(drawingDoc.DisplayName)
            Else
                Dim partNumberFromModel As String = CleanFileName(GetModelProjectIProperty(referencedModel, "Part Number"))
                Dim descriptionFromModel As String = CleanFileName(GetModelProjectIProperty(referencedModel, "Description"))
                Dim revisionFromModel As String = CleanFileName(GetRevisionNumberOrDefault(referencedModel))
                Dim revisionComment As String = ""

                If revisionFromModel = "A" AndAlso IsRevisionNumberBlank(referencedModel) Then
                    noRevisionCount += 1
                    revisionComment = "No revision number found; defaulted to REV A"
                    noRevisionFiles.AppendLine(drawingDoc.DisplayName & " -> " & partNumberFromModel & " from " & referencedModel.DisplayName & " (" & revisionComment & ")" & vbCrLf & referenceSelectionDetails)
                End If

                Dim today As String = Now.ToString("yyyy-MM-dd")
                Dim pdfName As String = partNumberFromModel & " - " & descriptionFromModel & " - REV " & revisionFromModel & " - " & today & ".pdf"
                outputPath = System.IO.Path.Combine(outputFolder, pdfName)
            End If

            ' Save the drawing first so the PDF always represents the edits that
            ' were present when this rule was started. If saving fails, the outer
            ' Catch records the drawing as failed and preserves any existing PDF.
            drawingDoc.Save()

            ' SaveCopyAs does not reliably replace an existing translator output.
            ' Remove the old dated PDF only after the drawing saved successfully,
            ' so the newly exported drawing is the authoritative PDF for this filename.
            If System.IO.File.Exists(outputPath) Then
                System.IO.File.Delete(outputPath)
                overwrittenCount += 1
            End If

            Dim context As TranslationContext = ThisApplication.TransientObjects.CreateTranslationContext()
            context.Type = kFileBrowseIOMechanism

            Dim options As NameValueMap = ThisApplication.TransientObjects.CreateNameValueMap()
            Dim data As DataMedium = ThisApplication.TransientObjects.CreateDataMedium()
            data.FileName = outputPath

            PDFAddIn.SaveCopyAs(drawingDoc, context, options, data)
            exportedCount += 1

            If referencedModel Is Nothing Then
                exportedFiles.AppendLine(drawingDoc.DisplayName & " -> " & outputPath)
            Else
                exportedFiles.AppendLine(drawingDoc.DisplayName & " -> " & outputPath & " [Referenced model: " & referencedModel.DisplayName & "]" & vbCrLf & referenceSelectionDetails)
            End If

        Catch ex As Exception
            failedCount += 1
            failedFiles.AppendLine(drawingDoc.DisplayName & " -> " & ex.Message)

        Finally
            Try
                drawingDoc.Close(True)
            Catch
                ' Do not block the batch when a drawing cannot be closed.
            End Try
        End Try
    Next

    Dim reportTime As String = Now.ToString("yyyy-MM-dd_HH-mm-ss")
    Dim reportPath As String = System.IO.Path.Combine(outputFolder, "PDF_Export_Report_" & reportTime & ".txt")
    Dim reportText As New System.Text.StringBuilder()
    reportText.AppendLine("iLogic PDF Batch Export Report")
    reportText.AppendLine("Run Time: " & Now.ToString("yyyy-MM-dd HH:mm:ss"))
    reportText.AppendLine("")
    reportText.AppendLine("Exported: " & exportedCount)
    reportText.AppendLine("Existing PDFs overwritten: " & overwrittenCount)
    reportText.AppendLine("No reference model (exported by drawing file name): " & noReferenceCount)
    reportText.AppendLine("No revision number found (defaulted to REV A): " & noRevisionCount)
    reportText.AppendLine("Failed: " & failedCount)
    reportText.AppendLine("")
    AppendReportSection(reportText, "Exported Files:", exportedFiles)
    AppendReportSection(reportText, "Drawings Without Reference Model:", noReferenceFiles)
    AppendReportSection(reportText, "Drawings With Blank Revision Number (Defaulted to REV A):", noRevisionFiles)
    AppendReportSection(reportText, "Failed Files:", failedFiles)
    System.IO.File.WriteAllText(reportPath, reportText.ToString())

    MessageBox.Show("Batch export complete." & vbCrLf & _
                    "Exported: " & exportedCount & vbCrLf & _
                    "Existing PDFs overwritten: " & overwrittenCount & vbCrLf & _
                    "No reference model (exported by file name): " & noReferenceCount & vbCrLf & _
                    "No revision number found (defaulted to REV A): " & noRevisionCount & vbCrLf & _
                    "Failed: " & failedCount & vbCrLf & _
                    "Report: " & reportPath, "iLogic PDF Batch Export")
End Sub

Sub AppendReportSection(ByVal reportText As System.Text.StringBuilder, ByVal heading As String, ByVal entries As System.Text.StringBuilder)
    reportText.AppendLine(heading)
    If entries.Length = 0 Then
        reportText.AppendLine("- None")
    Else
        reportText.Append(entries.ToString())
    End If
    reportText.AppendLine("")
End Sub

Function CleanFileName(ByVal fileName As String) As String
    For Each c As Char In System.IO.Path.GetInvalidFileNameChars()
        fileName = fileName.Replace(c, "")
    Next
    Return fileName.Trim()
End Function

Function GetBestReferencedModelFromDrawing(ByVal drawingDoc As DrawingDocument, ByRef selectionDetails As String) As Document
    Dim candidates As New System.Collections.ArrayList()
    AddDrawingViewModelCandidates(drawingDoc, candidates)
    AddDescriptorModelCandidates(drawingDoc, candidates)

    Dim details As New System.Text.StringBuilder()
    details.AppendLine("Candidate referenced model scoring:")
    If candidates.Count = 0 Then
        details.AppendLine("- No part/assembly candidates found")
        selectionDetails = details.ToString()
        Return Nothing
    End If

    Dim drawingName As String = System.IO.Path.GetFileNameWithoutExtension(drawingDoc.DisplayName).ToUpper()
    Dim bestModel As Document = Nothing
    Dim bestScore As Integer = -1
    For Each candidateObj As Object In candidates
        Dim candidateModel As Document = CType(candidateObj, Document)
        Dim score As Integer = ScoreReferencedModel(candidateModel, drawingName)
        details.AppendLine("- " & candidateModel.DisplayName & " | Score: " & score & " | Part Number: " & GetModelProjectIProperty(candidateModel, "Part Number") & " | Description: " & GetModelProjectIProperty(candidateModel, "Description") & " | Revision Number read: " & GetModelProjectIProperty(candidateModel, "Revision Number"))
        If score > bestScore Then
            bestScore = score
            bestModel = candidateModel
        End If
    Next

    details.AppendLine("Selected referenced model: " & bestModel.DisplayName & " | Score: " & bestScore)
    selectionDetails = details.ToString()
    Return bestModel
End Function

Sub AddDrawingViewModelCandidates(ByVal drawingDoc As DrawingDocument, ByVal candidates As System.Collections.ArrayList)
    For Each drawingSheet As Sheet In drawingDoc.Sheets
        For Each drawingView As DrawingView In drawingSheet.DrawingViews
            Try
                If Not drawingView.ReferencedDocumentDescriptor Is Nothing Then
                    AddCandidateModel(drawingView.ReferencedDocumentDescriptor.ReferencedDocument, candidates)
                End If
            Catch
                ' Continue if the view cannot resolve its model.
            End Try
        Next
    Next
End Sub

Sub AddDescriptorModelCandidates(ByVal drawingDoc As DrawingDocument, ByVal candidates As System.Collections.ArrayList)
    For Each refDesc As DocumentDescriptor In drawingDoc.ReferencedDocumentDescriptors
        Try
            If refDesc.ReferencedDocumentType = kPartDocumentObject Or refDesc.ReferencedDocumentType = kAssemblyDocumentObject Then
                AddCandidateModel(refDesc.ReferencedDocument, candidates)
            End If
        Catch
            ' Continue if the descriptor cannot resolve.
        End Try
    Next
End Sub

Sub AddCandidateModel(ByVal modelDoc As Document, ByVal candidates As System.Collections.ArrayList)
    If modelDoc Is Nothing Then Exit Sub
    If Not (modelDoc.DocumentType = kPartDocumentObject Or modelDoc.DocumentType = kAssemblyDocumentObject) Then Exit Sub

    For Each candidateObj As Object In candidates
        Dim existingModel As Document = CType(candidateObj, Document)
        Try
            If System.String.Equals(existingModel.FullFileName, modelDoc.FullFileName, System.StringComparison.OrdinalIgnoreCase) Then Exit Sub
        Catch
            If System.String.Equals(existingModel.DisplayName, modelDoc.DisplayName, System.StringComparison.OrdinalIgnoreCase) Then Exit Sub
        End Try
    Next
    candidates.Add(modelDoc)
End Sub

Function ScoreReferencedModel(ByVal modelDoc As Document, ByVal drawingName As String) As Integer
    Dim score As Integer = 0
    Dim partNumber As String = GetModelProjectIProperty(modelDoc, "Part Number")
    Dim description As String = GetModelProjectIProperty(modelDoc, "Description")
    Dim revisionNumber As String = GetModelProjectIProperty(modelDoc, "Revision Number")

    If revisionNumber.Trim() <> "" Then score += 1000
    If partNumber.Trim() <> "" Then
        score += 100
        If drawingName.Contains(partNumber.Trim().ToUpper()) Then score += 500
    End If
    If description.Trim() <> "" Then score += 25
    If drawingName <> "" AndAlso modelDoc.DisplayName.ToUpper().Contains(drawingName) Then score += 100
    If modelDoc.DocumentType = kAssemblyDocumentObject Then score += 10
    Return score
End Function

Function GetModelProjectIProperty(ByVal modelDoc As Document, ByVal propertyName As String) As String
    Dim directValue As String = GetPropertyValueFromPropertySets(modelDoc, propertyName)
    If directValue.Trim() <> "" Then Return directValue.Trim()

    Try
        Dim iLogicValue As Object = iProperties.Value(modelDoc.FullFileName, "Project", propertyName)
        If Not iLogicValue Is Nothing AndAlso CStr(iLogicValue).Trim() <> "" Then Return CStr(iLogicValue).Trim()
    Catch
    End Try
    Try
        Dim iLogicValue As Object = iProperties.Value(modelDoc.DisplayName, "Project", propertyName)
        If Not iLogicValue Is Nothing AndAlso CStr(iLogicValue).Trim() <> "" Then Return CStr(iLogicValue).Trim()
    Catch
    End Try
    Return ""
End Function

Function GetPropertyValueFromPropertySets(ByVal modelDoc As Document, ByVal propertyName As String) As String
    Dim value As String = GetPropertyValueFromNamedSet(modelDoc, "Design Tracking Properties", propertyName)
    If value.Trim() <> "" Then Return value.Trim()
    value = GetPropertyValueFromNamedSet(modelDoc, "{32853F0F-3444-11D1-9E93-0060B03C1CA6}", propertyName)
    If value.Trim() <> "" Then Return value.Trim()
    Try
        For Each propSet As PropertySet In modelDoc.PropertySets
            For Each prop As Object In propSet
                If System.String.Equals(prop.Name, propertyName, System.StringComparison.OrdinalIgnoreCase) AndAlso Not prop.Value Is Nothing Then Return CStr(prop.Value).Trim()
            Next
        Next
    Catch
    End Try
    Return ""
End Function

Function GetPropertyValueFromNamedSet(ByVal modelDoc As Document, ByVal propertySetName As String, ByVal propertyName As String) As String
    Try
        Dim modelProps As PropertySet = modelDoc.PropertySets.Item(propertySetName)
        Dim propValue As Object = modelProps.Item(propertyName).Value
        If propValue Is Nothing Then Return ""
        Return CStr(propValue).Trim()
    Catch
        Return ""
    End Try
End Function

Function IsRevisionNumberBlank(ByVal modelDoc As Document) As Boolean
    Return GetModelProjectIProperty(modelDoc, "Revision Number").Trim() = ""
End Function

Function GetRevisionNumberOrDefault(ByVal modelDoc As Document) As String
    Dim revisionValue As String = GetModelProjectIProperty(modelDoc, "Revision Number")
    If revisionValue.Trim() = "" Then Return "A"
    Return revisionValue.Trim().ToUpper()
End Function
