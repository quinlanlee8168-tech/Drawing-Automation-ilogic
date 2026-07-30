'========================================
' iLogic Rule: Batch Export Open Drawings to PDF and Close
' Option 1: Manual trigger after users finish edits
'
' PDF filenames use the referenced part/subassembly model iProperties:
' Project -> Part Number
' Project -> Description
' Project -> Revision Number
'
' If Project -> Revision Number is blank or missing, REV defaults to A and
' the run report records: No revision number found; defaulted to REV A
'========================================

Sub Main()
    ' Get Desktop path using .NET System namespace
    Dim desktopPath As String = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
    Dim outputFolder As String = desktopPath & "\Inventor_PDF_Output"

    ' Create folder if it doesn't exist
    If Not System.IO.Directory.Exists(outputFolder) Then
        System.IO.Directory.CreateDirectory(outputFolder)
    End If

    Dim exportedCount As Integer = 0
    Dim skippedCount As Integer = 0
    Dim failedCount As Integer = 0
    Dim noReferenceCount As Integer = 0
    Dim noRevisionCount As Integer = 0

    Dim exportedFiles As New System.Text.StringBuilder()
    Dim noReferenceFiles As New System.Text.StringBuilder()
    Dim noRevisionFiles As New System.Text.StringBuilder()
    Dim failedFiles As New System.Text.StringBuilder()
    Dim reservedOutputPaths As New System.Collections.Generic.HashSet(Of String)(System.StringComparer.OrdinalIgnoreCase)

    ' Get PDF Translator Add-In once
    Dim PDFAddIn As ApplicationAddIn
    PDFAddIn = ThisApplication.ApplicationAddIns.ItemById("{0AC6FD96-2F4D-42CE-8BE0-8AEA580399E4}")

    ' Snapshot drawings first, then process/close to avoid mutating the live documents collection while iterating
    Dim drawingsToProcess As New System.Collections.ArrayList()
    For Each openDoc As Document In ThisApplication.Documents
        Try
            If openDoc.DocumentType = kDrawingDocumentObject Then
                drawingsToProcess.Add(openDoc)
            End If
        Catch
            ' Ignore inaccessible document handles during collection build
        End Try
    Next

    For Each drawingObj As Object In drawingsToProcess

        Dim drawingDoc As DrawingDocument = CType(drawingObj, DrawingDocument)

        Try
            ' Find the best referenced Part or Assembly document from the drawing.
            ' Some drawings list extra references first; choose the referenced model
            ' with usable iProperties/revision data instead of defaulting to REV A.
            Dim referenceSelectionDetails As String = ""
            Dim referencedModel As Document = GetBestReferencedModelFromDrawing(drawingDoc, referenceSelectionDetails)

            If referencedModel Is Nothing Then
                noReferenceCount += 1

                ' No referenced model: export using drawing file name only
                Dim drawingFileNameOnly As String = System.IO.Path.GetFileNameWithoutExtension(drawingDoc.DisplayName)
                Dim invalidChars() As Char = System.IO.Path.GetInvalidFileNameChars()
                For Each c As Char In invalidChars
                    drawingFileNameOnly = drawingFileNameOnly.Replace(c, "")
                Next

                Dim outputPath As String = outputFolder & "\" & drawingFileNameOnly & ".pdf"
                outputPath = GetUniqueOutputPath(outputPath, outputFolder, drawingFileNameOnly, reservedOutputPaths)
                reservedOutputPaths.Add(outputPath)

                ' Create PDF translation objects
                Dim context As TranslationContext
                context = ThisApplication.TransientObjects.CreateTranslationContext()
                context.Type = kFileBrowseIOMechanism

                Dim options As NameValueMap
                options = ThisApplication.TransientObjects.CreateNameValueMap()

                Dim data As DataMedium
                data = ThisApplication.TransientObjects.CreateDataMedium()
                data.FileName = outputPath

                PDFAddIn.SaveCopyAs(drawingDoc, context, options, data)
                exportedCount += 1
                exportedFiles.AppendLine(drawingDoc.DisplayName & " -> " & outputPath)
                noReferenceFiles.AppendLine(drawingDoc.DisplayName)
            Else
                ' Always read naming fields from the referenced model iProperties
                Dim partNumberFromModel As String = GetModelProjectIProperty(referencedModel, "Part Number")
                Dim descriptionFromModel As String = GetModelProjectIProperty(referencedModel, "Description")
                Dim revisionFromModel As String = GetRevisionNumberOrDefault(referencedModel)
                Dim revisionComment As String = ""
                Dim drawingFileNameOnly As String = System.IO.Path.GetFileNameWithoutExtension(drawingDoc.DisplayName)

                If revisionFromModel = "A" AndAlso IsRevisionNumberBlank(referencedModel) Then
                    noRevisionCount += 1
                    revisionComment = "No revision number found; defaulted to REV A"
                    noRevisionFiles.AppendLine(drawingDoc.DisplayName & " -> " & partNumberFromModel & " from " & referencedModel.DisplayName & " (" & revisionComment & ")" & vbCrLf & referenceSelectionDetails)
                End If

                ' Clean invalid characters for file name
                Dim invalidChars() As Char = System.IO.Path.GetInvalidFileNameChars()
                For Each c As Char In invalidChars
                    partNumberFromModel = partNumberFromModel.Replace(c, "")
                    descriptionFromModel = descriptionFromModel.Replace(c, "")
                    revisionFromModel = revisionFromModel.Replace(c, "")
                    drawingFileNameOnly = drawingFileNameOnly.Replace(c, "")
                Next

                ' Add today's date and model revision number
                Dim today As String = Now.ToString("yyyy-MM-dd")
                Dim pdfName As String = partNumberFromModel & " - " & descriptionFromModel & " - REV " & revisionFromModel & " - " & today & ".pdf"
                Dim outputPath As String = outputFolder & "\" & pdfName

                ' Fallback naming when multiple drawings resolve to same Part Number + Description + REV name
                ' (still based on referenced model iProperties: Part Number + drawing file name + REV)
                If reservedOutputPaths.Contains(outputPath) Or System.IO.File.Exists(outputPath) Then
                    Dim fallbackPdfName As String = partNumberFromModel & " - " & drawingFileNameOnly & " - REV " & revisionFromModel & " - " & today & ".pdf"
                    outputPath = outputFolder & "\" & fallbackPdfName
                End If

                outputPath = GetUniqueOutputPath(outputPath, outputFolder, System.IO.Path.GetFileNameWithoutExtension(outputPath), reservedOutputPaths)
                reservedOutputPaths.Add(outputPath)

                ' Create PDF translation objects
                Dim context As TranslationContext
                context = ThisApplication.TransientObjects.CreateTranslationContext()
                context.Type = kFileBrowseIOMechanism

                Dim options As NameValueMap
                options = ThisApplication.TransientObjects.CreateNameValueMap()

                Dim data As DataMedium
                data = ThisApplication.TransientObjects.CreateDataMedium()
                data.FileName = outputPath

                ' Export PDF
                PDFAddIn.SaveCopyAs(drawingDoc, context, options, data)
                exportedCount += 1
                If revisionComment = "" Then
                    exportedFiles.AppendLine(drawingDoc.DisplayName & " -> " & outputPath & " [Referenced model: " & referencedModel.DisplayName & " | Part Number: " & partNumberFromModel & " | REV read: " & revisionFromModel & "]" & vbCrLf & referenceSelectionDetails)
                Else
                    exportedFiles.AppendLine(drawingDoc.DisplayName & " -> " & outputPath & " [Referenced model: " & referencedModel.DisplayName & " | Part Number: " & partNumberFromModel & " | REV read: " & revisionFromModel & "] (" & revisionComment & ")" & vbCrLf & referenceSelectionDetails)
                End If
            End If

        Catch ex As Exception
            failedCount += 1
            failedFiles.AppendLine(drawingDoc.DisplayName & " -> " & ex.Message)

        Finally
            ' Close drawing to reduce screen clutter (do not block batch on close issues)
            Try
                drawingDoc.Close(True)
            Catch
            End Try
        End Try

    Next

    ' Create run report text file
    Dim reportTime As String = Now.ToString("yyyy-MM-dd_HH-mm-ss")
    Dim reportPath As String = outputFolder & "\PDF_Export_Report_" & reportTime & ".txt"

    Dim reportText As New System.Text.StringBuilder()
    reportText.AppendLine("iLogic PDF Batch Export Report")
    reportText.AppendLine("Run Time: " & Now.ToString("yyyy-MM-dd HH:mm:ss"))
    reportText.AppendLine("")
    reportText.AppendLine("Exported: " & exportedCount)
    reportText.AppendLine("No reference model (exported by drawing file name): " & noReferenceCount)
    reportText.AppendLine("No revision number found (defaulted to REV A): " & noRevisionCount)
    reportText.AppendLine("Skipped: " & skippedCount)
    reportText.AppendLine("Failed: " & failedCount)
    reportText.AppendLine("")
    reportText.AppendLine("Exported Files:")
    If exportedFiles.Length = 0 Then
        reportText.AppendLine("- None")
    Else
        reportText.Append(exportedFiles.ToString())
    End If
    reportText.AppendLine("")
    reportText.AppendLine("Drawings Without Reference Model:")
    If noReferenceFiles.Length = 0 Then
        reportText.AppendLine("- None")
    Else
        reportText.Append(noReferenceFiles.ToString())
    End If
    reportText.AppendLine("")
    reportText.AppendLine("Drawings With Blank Revision Number (Defaulted to REV A):")
    If noRevisionFiles.Length = 0 Then
        reportText.AppendLine("- None")
    Else
        reportText.Append(noRevisionFiles.ToString())
    End If
    reportText.AppendLine("")
    reportText.AppendLine("Failed Files:")
    If failedFiles.Length = 0 Then
        reportText.AppendLine("- None")
    Else
        reportText.Append(failedFiles.ToString())
    End If

    System.IO.File.WriteAllText(reportPath, reportText.ToString())

    MessageBox.Show("Batch export complete." & vbCrLf & _
                    "Exported: " & exportedCount & vbCrLf & _
                    "No reference model (exported by file name): " & noReferenceCount & vbCrLf & _
                    "No revision number found (defaulted to REV A): " & noRevisionCount & vbCrLf & _
                    "Skipped (no model reference): " & skippedCount & vbCrLf & _
                    "Failed: " & failedCount & vbCrLf & _
                    "Report: " & reportPath, _
                    "iLogic PDF Batch Export")
End Sub

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
        Dim candidatePartNumber As String = GetModelProjectIProperty(candidateModel, "Part Number")
        Dim candidateDescription As String = GetModelProjectIProperty(candidateModel, "Description")
        Dim candidateRevision As String = GetModelProjectIProperty(candidateModel, "Revision Number")

        details.AppendLine("- " & candidateModel.DisplayName & " | Score: " & score & " | Part Number: " & candidatePartNumber & " | Description: " & candidateDescription & " | Revision Number read: " & candidateRevision)

        If score > bestScore Then
            bestScore = score
            bestModel = candidateModel
        End If
    Next

    If Not bestModel Is Nothing Then
        details.AppendLine("Selected referenced model: " & bestModel.DisplayName & " | Score: " & bestScore)
    End If

    selectionDetails = details.ToString()
    Return bestModel
End Function

Sub AddDrawingViewModelCandidates(ByVal drawingDoc As DrawingDocument, ByVal candidates As System.Collections.ArrayList)
    ' Prefer models behind the actual drawing views. In some drawings,
    ' ReferencedDocumentDescriptors can include extra part/assembly references before
    ' the primary model, which can cause the wrong iProperties/REV to be used.
    For Each drawingSheet As Sheet In drawingDoc.Sheets
        For Each drawingView As DrawingView In drawingSheet.DrawingViews
            Try
                If Not drawingView.ReferencedDocumentDescriptor Is Nothing Then
                    AddCandidateModel(drawingView.ReferencedDocumentDescriptor.ReferencedDocument, candidates)
                End If
            Catch
                ' Continue to the next view if this view cannot resolve its model.
            End Try
        Next
    Next
End Sub

Sub AddDescriptorModelCandidates(ByVal drawingDoc As DrawingDocument, ByVal candidates As System.Collections.ArrayList)
    For Each refDesc As DocumentDescriptor In drawingDoc.ReferencedDocumentDescriptors
        Try
            If refDesc.ReferencedDocumentType = kPartDocumentObject _
               Or refDesc.ReferencedDocumentType = kAssemblyDocumentObject Then
                AddCandidateModel(refDesc.ReferencedDocument, candidates)
            End If
        Catch
            ' Continue to the next descriptor if this one cannot resolve.
        End Try
    Next
End Sub

Sub AddCandidateModel(ByVal modelDoc As Document, ByVal candidates As System.Collections.ArrayList)
    If modelDoc Is Nothing Then
        Exit Sub
    End If

    If Not (modelDoc.DocumentType = kPartDocumentObject Or modelDoc.DocumentType = kAssemblyDocumentObject) Then
        Exit Sub
    End If

    For Each candidateObj As Object In candidates
        Dim existingModel As Document = CType(candidateObj, Document)
        Try
            If System.String.Equals(existingModel.FullFileName, modelDoc.FullFileName, System.StringComparison.OrdinalIgnoreCase) Then
                Exit Sub
            End If
        Catch
            If System.String.Equals(existingModel.DisplayName, modelDoc.DisplayName, System.StringComparison.OrdinalIgnoreCase) Then
                Exit Sub
            End If
        End Try
    Next

    candidates.Add(modelDoc)
End Sub

Function ScoreReferencedModel(ByVal modelDoc As Document, ByVal drawingName As String) As Integer
    Dim score As Integer = 0
    Dim partNumber As String = GetModelProjectIProperty(modelDoc, "Part Number")
    Dim description As String = GetModelProjectIProperty(modelDoc, "Description")
    Dim revisionNumber As String = GetModelProjectIProperty(modelDoc, "Revision Number")
    Dim modelDisplayName As String = modelDoc.DisplayName.ToUpper()

    ' Highest priority: use a model that actually has a revision number.
    If revisionNumber.Trim() <> "" Then
        score += 1000
    End If

    If partNumber.Trim() <> "" Then
        score += 100
        If drawingName.Contains(partNumber.Trim().ToUpper()) Then
            score += 500
        End If
    End If

    If description.Trim() <> "" Then
        score += 25
    End If

    If drawingName <> "" AndAlso modelDisplayName.Contains(drawingName) Then
        score += 100
    End If

    If modelDoc.DocumentType = kAssemblyDocumentObject Then
        score += 10
    End If

    Return score
End Function

Function GetModelProjectIProperty(ByVal modelDoc As Document, ByVal propertyName As String) As String
    ' Read directly from the referenced model document first. This is the most
    ' important path for Revision Number because the PDF name must come from the
    ' model's Project iProperties, not from the drawing.
    Dim directValue As String = GetPropertyValueFromPropertySets(modelDoc, propertyName)
    If directValue.Trim() <> "" Then
        Return directValue.Trim()
    End If

    ' iLogic can also read model iProperties through the iProperties helper. Use
    ' it as a fallback for environments where the raw PropertySets call is blank.
    Try
        Dim iLogicValue As Object = iProperties.Value(modelDoc.FullFileName, "Project", propertyName)
        If Not iLogicValue Is Nothing AndAlso CStr(iLogicValue).Trim() <> "" Then
            Return CStr(iLogicValue).Trim()
        End If
    Catch
    End Try

    Try
        Dim iLogicValue As Object = iProperties.Value(modelDoc.DisplayName, "Project", propertyName)
        If Not iLogicValue Is Nothing AndAlso CStr(iLogicValue).Trim() <> "" Then
            Return CStr(iLogicValue).Trim()
        End If
    Catch
    End Try

    Return ""
End Function

Function GetPropertyValueFromPropertySets(ByVal modelDoc As Document, ByVal propertyName As String) As String
    ' First try the normal Inventor display name for the Project tab properties.
    Dim value As String = GetPropertyValueFromNamedSet(modelDoc, "Design Tracking Properties", propertyName)
    If value.Trim() <> "" Then
        Return value.Trim()
    End If

    ' Then try the internal GUID for Design Tracking Properties.
    value = GetPropertyValueFromNamedSet(modelDoc, "{32853F0F-3444-11D1-9E93-0060B03C1CA6}", propertyName)
    If value.Trim() <> "" Then
        Return value.Trim()
    End If

    ' Final fallback: scan every property set for an exact property-name match.
    Try
        For Each propSet As PropertySet In modelDoc.PropertySets
            For Each prop As Object In propSet
                If System.String.Equals(prop.Name, propertyName, System.StringComparison.OrdinalIgnoreCase) Then
                    If Not prop.Value Is Nothing Then
                        Return CStr(prop.Value).Trim()
                    End If
                End If
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
        If propValue Is Nothing Then
            Return ""
        End If

        Return CStr(propValue).Trim()
    Catch
        Return ""
    End Try
End Function

Function IsRevisionNumberBlank(ByVal modelDoc As Document) As Boolean
    Dim revisionValue As String = GetModelProjectIProperty(modelDoc, "Revision Number")
    Return revisionValue.Trim() = ""
End Function

Function GetRevisionNumberOrDefault(ByVal modelDoc As Document) As String
    Dim revisionValue As String = GetModelProjectIProperty(modelDoc, "Revision Number")
    If revisionValue.Trim() = "" Then
        Return "A"
    End If

    Return revisionValue.Trim().ToUpper()
End Function

Function GetUniqueOutputPath(ByVal proposedPath As String, ByVal outputFolder As String, ByVal baseFileName As String, ByVal reservedOutputPaths As System.Collections.Generic.HashSet(Of String)) As String
    Dim candidatePath As String = proposedPath
    Dim suffix As Integer = 1

    Do While reservedOutputPaths.Contains(candidatePath) Or System.IO.File.Exists(candidatePath)
        candidatePath = outputFolder & "\" & baseFileName & " (" & suffix & ").pdf"
        suffix += 1
    Loop

    Return candidatePath
End Function
