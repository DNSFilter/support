<#
DNS Clarity Version 1.0 
Written by Jon Cohen 02/2020
Copyright (c) DNSFilter. All rights reserved.
#>

$Global:syncHash = [hashtable]::Synchronized(@{})
$newRunspace =[runspacefactory]::CreateRunspace()
$newRunspace.ApartmentState = "STA"
$newRunspace.ThreadOptions = "ReuseThread"
$newRunspace.Open()
$newRunspace.SessionStateProxy.SetVariable("syncHash",$syncHash)
$iss = [initialsessionstate]::Create()
$iss.ApartmentState = 'STA'
$iss.ThreadOptions = 'ReuseThread'
$iss.LanguageMode = 'FullLanguage'
$customRSPool = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1,4,$iss,$host)
$customRSPool.Open()
$ps = [powershell]::Create()
$ps.RunspacePool = $customRSPool
# Load WPF assembly if necessary
[void][System.Reflection.Assembly]::LoadWithPartialName('presentationframework')

$psCmd = [PowerShell]::Create().AddScript({
    [xml]$script:xaml = '<Window 
   
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:local="clr-namespace:WpfApp2"
        mc:Ignorable="d"
        Title="DNS Clarity" Height="400" Width="700" ResizeMode="NoResize" WindowStartupLocation="CenterScreen" WindowStyle="None" Background="Transparent" Foreground="Transparent">

        <Window.Resources>
<Style x:Key="FocusVisual">
    <Setter Property="Control.Template">
        <Setter.Value>
            <ControlTemplate>
                <Rectangle Margin="2" SnapsToDevicePixels="true" Stroke="{DynamicResource {x:Static SystemColors.ControlTextBrushKey}}" StrokeThickness="1" StrokeDashArray="1 2"/>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
<SolidColorBrush x:Key="Button.Static.Background" Color="Transparent"/>
<SolidColorBrush x:Key="Button.Static.Border" Color="Transparent"/>
<SolidColorBrush x:Key="Button.MouseOver.Background" Color="Transparent"/>
<SolidColorBrush x:Key="Button.MouseOver.Border" Color="Transparent"/>
<SolidColorBrush x:Key="Button.Pressed.Background" Color="Transparent"/>
<SolidColorBrush x:Key="Button.Pressed.Border" Color="#FFABADB3"/>
<SolidColorBrush x:Key="Button.Pressed.Foreground" Color="#FFABADB3"/>
<SolidColorBrush x:Key="Button.Disabled.Background" Color="Transparent"/>
<SolidColorBrush x:Key="Button.Disabled.Border" Color="#FFABADB3"/>
<SolidColorBrush x:Key="Button.Disabled.Foreground" Color="#FFABADB3"/>
<Style x:Key="MyButton" TargetType="{x:Type Button}">

    <Setter Property="FocusVisualStyle" Value="{StaticResource FocusVisual}"/>
    <Setter Property="Background" Value="{StaticResource Button.Static.Background}"/>
    <Setter Property="BorderBrush" Value="{StaticResource Button.Static.Border}"/>
    <Setter Property="Foreground" Value="{DynamicResource {x:Static SystemColors.ControlTextBrushKey}}"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="HorizontalContentAlignment" Value="Center"/>
    <Setter Property="VerticalContentAlignment" Value="Center"/>
    <Setter Property="Padding" Value="1"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="{x:Type Button}">
                <Border x:Name="border" BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}" Background="{TemplateBinding Background}" SnapsToDevicePixels="true">
                    <ContentPresenter x:Name="contentPresenter" Focusable="False" HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}" Margin="{TemplateBinding Padding}" RecognizesAccessKey="True" SnapsToDevicePixels="{TemplateBinding SnapsToDevicePixels}" VerticalAlignment="{TemplateBinding VerticalContentAlignment}"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsDefaulted" Value="true">
                        <Setter Property="BorderBrush" TargetName="border" Value="{DynamicResource {x:Static SystemColors.HighlightBrushKey}}"/>
                    </Trigger>
                    <Trigger Property="IsMouseOver" Value="true">
                        <Setter Property="Background" TargetName="border" Value="{StaticResource Button.MouseOver.Background}"/>
                        <Setter Property="BorderBrush" TargetName="border" Value="{StaticResource Button.MouseOver.Border}"/>
                    </Trigger>
                    <Trigger Property="Button.IsPressed" Value="true">
                        <Setter Property="Background" TargetName="border" Value="{StaticResource Button.Pressed.Background}"/>
                        <Setter Property="BorderBrush" TargetName="border" Value="{StaticResource Button.Pressed.Border}"/>
                    </Trigger>
                    <Trigger Property="IsEnabled" Value="false">
                        <Setter Property="Background" TargetName="border" Value="{StaticResource Button.Disabled.Background}"/>
                        <Setter Property="BorderBrush" TargetName="border" Value="{StaticResource Button.Disabled.Border}"/>
                        <Setter Property="TextElement.Foreground" TargetName="contentPresenter" Value="{StaticResource Button.Disabled.Foreground}"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
</Window.Resources>



    <Grid>
       
        
        <Image x:Name="Background" Stretch="UniformToFill"/>
        <Image x:Name="Logo" Margin="-535,-272,0,0"  Width="173" Height = "133"/>
        <TextBlock HorizontalAlignment="Left" Margin="0,-20,0,0" TextWrapping="Wrap" Text="DNS Clarity" VerticalAlignment="Top"/>  
       
        <Button x:Name="button1" Margin="-2,96,0,0" HorizontalAlignment="Left" VerticalAlignment="Top" Background="Transparent"   BorderThickness="0" Style="{StaticResource MyButton}" Width="310" Height = "53">
        <StackPanel>
        <Image Name="RunInactive"/>
        </StackPanel>
        </Button>


         <Button x:Name = "button2" Margin="-2,147,0,0" HorizontalAlignment="Left" VerticalAlignment="Top" Background="Transparent" BorderThickness="0" Style="{StaticResource MyButton}" Width="310" Height = "53">
            <StackPanel>
        <Image Name="ViewInactive"/>
        </StackPanel>
        </Button>


        <Button x:Name = "button3" Margin="-2,332,0,0" HorizontalAlignment="Left" VerticalAlignment="Top" Background="Transparent" BorderThickness="0" Style="{StaticResource MyButton}" Width="310" Height = "53" ToolTip = "Send us your results and any extra notes (Requires valid email associated with account) ">
            <StackPanel>
        <Image Name="SendInactive"/>
        </StackPanel>
        </Button>
        

        <Button x:Name = "button4" Margin="510,366,0,0" HorizontalAlignment="Left" VerticalAlignment="Top" Background="Transparent"  BorderThickness="0" Style="{StaticResource MyButton}" Width="80" Height = "34" ToolTip = "Enable Debug-mode on Roaming Client">
             <StackPanel>
        <Image Name="EnabledDBG"/>
        </StackPanel>
        </Button>


        <Button x:Name = "button5" Margin="582,366,0,0" HorizontalAlignment="Left" VerticalAlignment="Top" Background="Transparent" BorderThickness="0" Style="{StaticResource MyButton}" Width="80" Height = "34" ToolTip = "Disable Debug-mode on Roaming Client">
            <StackPanel>
        <Image Name="DisabledDBG"/>
        </StackPanel>
        </Button>



        
        <ProgressBar x:Name="ProgressBar" HorizontalAlignment="Left" Height="35" Margin="340,35,0,0" VerticalAlignment="Top" Width="327" Foreground="#FF2AA1D4"/>

        <TextBox x:Name="Userinput" HorizontalAlignment="Left" Height="20" TextWrapping="Wrap" Text="Type Valid Email" VerticalAlignment="Top" Width="168" Margin="62,255,0,0" Foreground="Gray" Background="#FF323232" IsEnabled = "False"/>

        <TextBox x:Name="Notes" HorizontalAlignment="Left" Height="43" TextWrapping="Wrap" Text="Notes and Comments" VerticalAlignment="Top" Width="168" Margin="62,280,0,0" Foreground="Gray" Background="#FF323232" IsEnabled = "False"/>

        <Image x:Name="RCNote" Margin="520,320,46,35" Width="100" Height="40" />
        
        <UserControl Content="DNS Clarity" HorizontalAlignment="Center" VerticalAlignment="Top" Width="703" Height="25" Grid.ColumnSpan="4" Margin="-3,-4,-4,0" Background="Gray"/>    

        <Button x:Name="button6" Content="X" Grid.Column="1" HorizontalAlignment="Left" Margin="675,0,0,0" VerticalAlignment="Top" Width="25" Height="21"/>   
             
        <TextBlock HorizontalAlignment="Left" Margin="1,3,0,0" TextWrapping="Wrap" Text="DNS Clarity" VerticalAlignment="Top" Height="16" Width="174" Grid.Column="1" FontFamily="Proxima soft" Foreground="#000000" FontSize="14" />
        
        <RichTextBox x:Name="log_txt" Grid.Column="1" HorizontalAlignment="Left" Height="178" Margin="340,91,0,0" VerticalAlignment="Top" Width="327" Background="Transparent" IsReadOnly="True" FontFamily="Sitka Text" Foreground="#FF2AA1D4">
            <FlowDocument>
                <Paragraph>
                    <Run Text="Waiting for input.."/>
                </Paragraph>
            </FlowDocument>
        </RichTextBox>
    </Grid>

</Window>'
#Load XAML
$script:form = [Windows.Markup.XamlReader]::Load((New-Object System.Xml.XmlNodeReader $xaml))
$xaml.SelectNodes("//*[@Name]") | ForEach-Object { Set-Variable -Name ($_.Name) -Value $form.FindName($_.Name) -Scope Script }

$AttributesToRemove = @(
        'x:Class',
        'mc:Ignorable'
    )

    foreach ($Attrib in $AttributesToRemove) {
        if ( $xaml.Window.GetAttribute($Attrib) ) {
             $xaml.Window.RemoveAttribute($Attrib)
        }
    }
    
    $reader=(New-Object System.Xml.XmlNodeReader $xaml)
    
    $syncHash.Window=[Windows.Markup.XamlReader]::Load( $reader )

    [xml]$XAML = $xaml
        $xaml.SelectNodes("//*[@*[contains(translate(name(.),'n','N'),'Name')]]") | %{
        #Find all of the form types and add them as members to the synchash
        $syncHash.Add($_.Name,$syncHash.Window.FindName($_.Name) )

    }

    $Script:JobCleanup = [hashtable]::Synchronized(@{})
    $Script:Jobs = [system.collections.arraylist]::Synchronized((New-Object System.Collections.ArrayList))
    $Window.Add_Closing({$_.Cancel = $true})
    #region Background runspace to clean up jobs
    $jobCleanup.Flag = $True
    $newRunspace =[runspacefactory]::CreateRunspace()
    $newRunspace.ApartmentState = "STA"
    $newRunspace.ThreadOptions = "ReuseThread"          
    $newRunspace.Open()        
    $newRunspace.SessionStateProxy.SetVariable("jobCleanup",$jobCleanup)     
    $newRunspace.SessionStateProxy.SetVariable("jobs",$jobs) 
    $jobCleanup.PowerShell = [PowerShell]::Create().AddScript({
        #Routine to handle completed runspaces
        Do {    
            Foreach($runspace in $jobs) {            
                If ($runspace.Runspace.isCompleted) {
                    [void]$runspace.powershell.EndInvoke($runspace.Runspace)
                    $runspace.powershell.dispose()
                    $runspace.Runspace = $null
                    $runspace.powershell = $null               
                } 
            }
            #Clean out unused runspace jobs
            $temphash = $jobs.clone()
            $temphash | Where {
                $_.runspace -eq $Null
            } | ForEach {
                $jobs.remove($_)
            }        
            Start-Sleep -Seconds 1     
        } while ($jobCleanup.Flag)
    })
    $jobCleanup.PowerShell.Runspace = $newRunspace
    $jobCleanup.Thread = $jobCleanup.PowerShell.BeginInvoke() 
   
   $synchash.window.add_MouseLeftButtonDown({
    $synchash.window.DragMove()
})

# ===========================================

#Logo B64
$base64 = "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
8OAoD/H0K0kPv+/PTFAAAAAElFTkSuQmCC"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap1 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap1.BeginInit()
$bitmap1.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64)
$bitmap1.EndInit()
# Freeze() prevents memory leaks.
$bitmap1.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.Logo.source = $bitmap1



#RCNote B64
$base64a = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap2 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap2.BeginInit()
$bitmap2.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64a)
$bitmap2.EndInit()
# Freeze() prevents memory leaks.
$bitmap2.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.RCNote.source = $bitmap2


#Background B64
$base64b = "iVBORw0KGgoAAAANSUhEUgAAArwAAAGQCAIAAADDXiTEAAABJ2lDQ1BBcHBsZSBSR0IAACiRlY+9SsNQGIaf04qCQxEJbsLBQVzEn61j0pYiONQokmRrkkMVbXI4Of506k14EQ4ujoLeQcVBcPIS3ARxcHCIEJxKn+n53uHl/aC24ba9Tm0Jhpk1fteTQRjJhRfmqQNAPym02+vtA2R5pviPgK83BMDrptv2OszGYqKNBX6A3VQVCYhtIL2y2oK4AZz4TFsQt4BjjvwWiEegMSh9AjTi0t+BhgnCCMQH4AyCMIIagBOX7gCOVdcWoJXrkTkdnFi502
w2pZvmsZKHo8KqYSH3siQ3Ojd9q1Kg3FfudrU+V9LvejM+PI0gjGRpnwcIQKxMqqwiuTCXfyrE8/S76hg9gevD3EOVHX/D3Ras1qtsfQ2Wx3CvfwHzpVA+dKJVLAAAAAlwSFlzAAALEwAACxMBAJqcGAAAE+lpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IkFkb2Jl
IFhNUCBDb3JlIDUuNi1jMTQ4IDc5LjE2NDAzNiwgMjAxOS8wOC8xMy0wMTowNjo1NyAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczpwaG90b3Nob3A9Imh0dHA6Ly9ucy5hZG9iZS5jb20vcGhvdG9zaG9wLzEuMC
8iIHhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hv
cCBDQyAyMDE5IChNYWNpbnRvc2gpIiB4bXA6Q3JlYXRlRGF0ZT0iMjAyMC0wMS0xNlQxNTo0MjozOS0wNTowMCIgeG1wOk1ldGFkYXRhRGF0ZT0iMjAyMC0wMi0wM1QxNzo0NTozNC0wNTowMCIgeG1wOk1vZGlmeURhdGU9IjIwMjAtMDItMDNUMTc6NDU6MzQtMDU6MDAiIHBob3Rvc2hvcDpDb2xvck1vZGU9IjMiIHBob3Rvc2hvcDpJQ0NQcm9maWxlPSJBcHBsZSBSR0IiIGRjOmZvcm1hdD0iaW1hZ2UvcG5nIiB4bXBNTTpJbnN0YW5jZU
lEPSJ4bXAuaWlkOjkzZDU0OTUwLWYwOGItNDBlYi1hYzY0LTNlMDliY2MxYmRmMyIgeG1wTU06RG9jdW1lbnRJRD0iYWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOjQyODEwYzRlLWRjMmYtYjg0Zi04ZjU3LWZiYmNkYjQ0YTA0OSIgeG1wTU06T3JpZ2luYWxEb2N1bWVudElEPSJ4bXAuZGlkOjg3MWJkMmE3LTY5ZTgtNDkxOC05ZTBjLWU4ZWQyMGJjM2RkYSI+IDxwaG90b3Nob3A6VGV4dExheWVycz4gPHJkZjpCYWc+IDxyZGY6bGkgcGhvdG9z
aG9wOkxheWVyTmFtZT0ib2ZmIiBwaG90b3Nob3A6TGF5ZXJUZXh0PSJvZmYiLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJvbiIgcGhvdG9zaG9wOkxheWVyVGV4dD0ib24iLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJvbiIgcGhvdG9zaG9wOkxheWVyVGV4dD0ib24iLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJvZmYiIHBob3Rvc2hvcDpMYXllclRleHQ9Im9mZiIvPiA8cmRmOmxpIHBob3Rvc2hvcD
pMYXllck5hbWU9IlJvYW1pbmcgQ2xpZW50IERlYnVnIE1vZGUiIHBob3Rvc2hvcDpMYXllclRleHQ9IlJvYW1pbmcgQ2xpZW50IERlYnVnIE1vZGUiLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJEaXNhYmxlZCIgcGhvdG9zaG9wOkxheWVyVGV4dD0iRGlzYWJsZWQiLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJFbmFibGVkIiBwaG90b3Nob3A6TGF5ZXJUZXh0PSJFbmFibGVkIi8+IDxyZGY6bGkgcGhvdG9zaG9w
OkxheWVyTmFtZT0iRGlzYWJsZWQiIHBob3Rvc2hvcDpMYXllclRleHQ9IkRpc2FibGVkIi8+IDxyZGY6bGkgcGhvdG9zaG9wOkxheWVyTmFtZT0iRW5hYmxlZCIgcGhvdG9zaG9wOkxheWVyVGV4dD0iRW5hYmxlZCIvPiA8cmRmOmxpIHBob3Rvc2hvcDpMYXllck5hbWU9IlJ1biBUb29sIiBwaG90b3Nob3A6TGF5ZXJUZXh0PSJSdW4gVG9vbCIvPiA8cmRmOmxpIHBob3Rvc2hvcDpMYXllck5hbWU9IlJ1biBUb29sIiBwaG90b3Nob3A6TG
F5ZXJUZXh0PSJSdW4gVG9vbCIvPiA8cmRmOmxpIHBob3Rvc2hvcDpMYXllck5hbWU9IlZpZXcgTG9ncyIgcGhvdG9zaG9wOkxheWVyVGV4dD0iVmlldyBMb2dzIi8+IDxyZGY6bGkgcGhvdG9zaG9wOkxheWVyTmFtZT0iVmlldyBMb2dzIiBwaG90b3Nob3A6TGF5ZXJUZXh0PSJWaWV3IExvZ3MiLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJTZW5kIExvZ3MiIHBob3Rvc2hvcDpMYXllclRleHQ9IlNlbmQgTG9ncyIvPiA8cmRm
OmxpIHBob3Rvc2hvcDpMYXllck5hbWU9IipQbGVhc2UgZW50ZXIgYSB2YWxpZCBlbWFpbCBiZWZvcmUgc3VibWl0dGluZyB5b3VyIGxvZ3MiIHBob3Rvc2hvcDpMYXllclRleHQ9IipQbGVhc2UgZW50ZXIgYSB2YWxpZCBlbWFpbCBiZWZvcmUgc3VibWl0dGluZyB5b3VyIGxvZ3MiLz4gPHJkZjpsaSBwaG90b3Nob3A6TGF5ZXJOYW1lPSJTZW5kIExvZ3MiIHBob3Rvc2hvcDpMYXllclRleHQ9IlNlbmQgTG9ncyIvPiA8cmRmOmxpIHBob3
Rvc2hvcDpMYXllck5hbWU9IlBsZWFzZSBmaWxsIG91dCB0aGUgZmllbGRzIGJlbG93IHRvIHNlbmQgeW91ciBsb2dzIHRvIHRoZSBzdXBwbyIgcGhvdG9zaG9wOkxheWVyVGV4dD0iUGxlYXNlIGZpbGwgb3V0IHRoZSBmaWVsZHMgYmVsb3cgdG8gc2VuZCB5b3VyIGxvZ3MgdG8gdGhlIHN1cHBvcnQgdGVhbSIvPiA8cmRmOmxpIHBob3Rvc2hvcDpMYXllck5hbWU9IlNlbmQgTG9ncyIgcGhvdG9zaG9wOkxheWVyVGV4dD0iU2VuZCBMb2dz
Ii8+IDwvcmRmOkJhZz4gPC9waG90b3Nob3A6VGV4dExheWVycz4gPHBob3Rvc2hvcDpEb2N1bWVudEFuY2VzdG9ycz4gPHJkZjpCYWc+IDxyZGY6bGk+QjFERDU2MzEzRTFCNERFOUVDMEMwOTk5OTYwMTBGMzY8L3JkZjpsaT4gPHJkZjpsaT5CREIxNDdCNTlEOEE1NUMyODMwQjkxQ0M5N0Q1N0U0NDwvcmRmOmxpPiA8cmRmOmxpPmFkb2JlOmRvY2lkOnBob3Rvc2hvcDozMTkzZWIwYi0wMzkwLTExZTUtOGVhNy04YTA2NWM4NjhkZjA8L3
JkZjpsaT4gPHJkZjpsaT5hZG9iZTpkb2NpZDpwaG90b3Nob3A6MzYxOGMwZDMtMDM5MC0xMWU1LThlYTctOGEwNjVjODY4ZGYwPC9yZGY6bGk+IDxyZGY6bGk+YWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOjU2YzE1ZjJjLTc0NTAtMTFlNS1hZDY5LTk5MzlhODBhYzVjMTwvcmRmOmxpPiA8cmRmOmxpPmFkb2JlOmRvY2lkOnBob3Rvc2hvcDpjNTg4YzJjNi0wM2E2LTExZTUtODYxYi1mMWI3NzlhNTc3MDY8L3JkZjpsaT4gPHJkZjpsaT5hZG9i
ZTpkb2NpZDpwaG90b3Nob3A6YzY0YWIwY2YtNzQ0ZS0xMWU1LWFkNjktOTkzOWE4MGFjNWMxPC9yZGY6bGk+IDxyZGY6bGk+YWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOmU0NTEwNjQ2LWIyMmUtMTFlNS1hZWRmLWFhNzdiZWNjMmU5NjwvcmRmOmxpPiA8cmRmOmxpPnhtcC5kaWQ6MGU1MmZhYjctNGMyYi00OTRkLTg5NmItYTkxZDg5MmQ1NjhlPC9yZGY6bGk+IDxyZGY6bGk+eG1wLmRpZDoyNDk2YzFhYi0wY2I3LTQ0NDItYTQ1Zi04ZWUwMT
I0ZGVjY2Q8L3JkZjpsaT4gPHJkZjpsaT54bXAuZGlkOjQwMjIxYzcwLTM5OWEtNDBjMi1iNDEzLTQ4Nzc0OTJiZGE3MjwvcmRmOmxpPiA8cmRmOmxpPnhtcC5kaWQ6NjJmZTVlNDYtZDExNC00OWJmLTkyNTItOWU2ZWI5OTQ5NTgxPC9yZGY6bGk+IDxyZGY6bGk+eG1wLmRpZDo2Zjk0MDRiNy04YzY2LTU4NDMtYTcwYy00NDdjNjE5YzJhZjE8L3JkZjpsaT4gPHJkZjpsaT54bXAuZGlkOmNkYjg4MWQzLWRkNWUtMDE0My04NjE0LWYwZDhj
YjVhMzAxMzwvcmRmOmxpPiA8cmRmOmxpPnhtcC5kaWQ6ZTc0ZTk0ZjQtMzJiMS05MzQxLTgwYWQtYzFlNDFiMTIzNGZiPC9yZGY6bGk+IDwvcmRmOkJhZz4gPC9waG90b3Nob3A6RG9jdW1lbnRBbmNlc3RvcnM+IDx4bXBNTTpIaXN0b3J5PiA8cmRmOlNlcT4gPHJkZjpsaSBzdEV2dDphY3Rpb249ImNyZWF0ZWQiIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6ODcxYmQyYTctNjllOC00OTE4LTllMGMtZThlZDIwYmMzZGRhIiBzdEV2dD
p3aGVuPSIyMDIwLTAxLTE2VDE1OjQyOjM5LTA1OjAwIiBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgQ0MgMjAxOSAoTWFjaW50b3NoKSIvPiA8cmRmOmxpIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6NWVhNWQ0MDEtNTBiOS00ODY4LTk0MWMtOGE4MDY1MmVmNjgzIiBzdEV2dDp3aGVuPSIyMDIwLTAxLTE2VDE2OjExOjQzLTA1OjAwIiBzdEV2dDpzb2Z0d2FyZUFnZW50PSJB
ZG9iZSBQaG90b3Nob3AgQ0MgMjAxOSAoTWFjaW50b3NoKSIgc3RFdnQ6Y2hhbmdlZD0iLyIvPiA8cmRmOmxpIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6M2FjN2RhZWQtM2JhMi00M2MwLTkxYjgtMDkyMGMwMTdmNDMwIiBzdEV2dDp3aGVuPSIyMDIwLTAyLTAzVDE3OjQ1OjM0LTA1OjAwIiBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgMjEuMCAoTWFjaW50b3NoKSIgc3RFdn
Q6Y2hhbmdlZD0iLyIvPiA8cmRmOmxpIHN0RXZ0OmFjdGlvbj0iY29udmVydGVkIiBzdEV2dDpwYXJhbWV0ZXJzPSJmcm9tIGFwcGxpY2F0aW9uL3ZuZC5hZG9iZS5waG90b3Nob3AgdG8gaW1hZ2UvcG5nIi8+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJkZXJpdmVkIiBzdEV2dDpwYXJhbWV0ZXJzPSJjb252ZXJ0ZWQgZnJvbSBhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIHRvIGltYWdlL3BuZyIvPiA8cmRmOmxpIHN0RXZ0OmFj
dGlvbj0ic2F2ZWQiIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6OTNkNTQ5NTAtZjA4Yi00MGViLWFjNjQtM2UwOWJjYzFiZGYzIiBzdEV2dDp3aGVuPSIyMDIwLTAyLTAzVDE3OjQ1OjM0LTA1OjAwIiBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgMjEuMCAoTWFjaW50b3NoKSIgc3RFdnQ6Y2hhbmdlZD0iLyIvPiA8L3JkZjpTZXE+IDwveG1wTU06SGlzdG9yeT4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3
RhbmNlSUQ9InhtcC5paWQ6M2FjN2RhZWQtM2JhMi00M2MwLTkxYjgtMDkyMGMwMTdmNDMwIiBzdFJlZjpkb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6YWJlYWRiZjMtYzhjZi01MjRlLTg3ZjItNDY5MDZiY2NjNWEyIiBzdFJlZjpvcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6ODcxYmQyYTctNjllOC00OTE4LTllMGMtZThlZDIwYmMzZGRhIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRh
PiA8P3hwYWNrZXQgZW5kPSJyIj8+HcjmvgAAGQhJREFUeJzt3X9wXnWd6PFTtPnRhDQNJiFNQ5uYlrah9AdSAha3lBXwthfUa4fqBalX/1DHGV3AcXplGMeLw9xxYJ3dRZi97lilujBdZdUiUDB0LaUBaUsbUpo2JcQm1PaBtKlt0zTi3D+OPD4mT+JHftb6eg3TSU6ec873fMPM8855zvOccXv37k2AU8ymTZtuvvnm7Lfjxo0b7ZHDfpT7bfbr0b7I/Xe0n462zdFGNcZQgb92Z7zTAwAA/jqIBgAgRDQAACGiAQAIEQ0AQIhoAABCRAMAECIaAI
AQ0QAAhIgGACBENAAAIaIBAAgRDQBAiGgAAEJEAwAQIhoAgBDRAACEiAYAIEQ0AAAhogEACBENAECIaAAAQkQDABAiGgCAENEAAISIBgAgRDQAACGiAQAIEQ0AQIhoAABCRAMAECIaAIAQ0QAAhIgGACBENAAAIaIBAAgRDQBAiGgAAEJEAwAQIhoAgBDRAACEiAYAIEQ0AAAhogEACBENAECIaAAAQkQDABAiGgCAENEAAISIBgAgRDQAACGiAQAIEQ0AQIhoAABCRAMAECIaAIAQ0QAAhIgGACBENAAAIaIBAAgRDQBAiGgAAEJEAwAQIhoAgBDR
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
+f+XjPo1VA1feQAAAABJRU5ErkJggg=="
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap3 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap3.BeginInit()
$bitmap3.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64b)
$bitmap3.EndInit()
# Freeze() prevents memory leaks.
$bitmap3.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.Background.source = $bitmap3


#Runinactive B64
$base64c = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap4 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap4.BeginInit()
$bitmap4.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64c)
$bitmap4.EndInit()
# Freeze() prevents memory leaks.
$bitmap4.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.RunInactive.source = $bitmap4

#ViewInactive B64
$base64d = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap5 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap5.BeginInit()
$bitmap5.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64d)
$bitmap5.EndInit()
# Freeze() prevents memory leaks.
$bitmap5.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.ViewInactive.source = $bitmap5

#SendInactive B64
$base64e = "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
ol63ZQAAAABJRU5ErkJggg=="
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap6 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap6.BeginInit()
$bitmap6.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64e)
$bitmap6.EndInit()
# Freeze() prevents memory leaks.
$bitmap6.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.SendInactive.source = $bitmap6

#EnabledDBG B64
$base64f = "iVBORw0KGgoAAAANSUhEUgAAAFAAAAAiCAYAAADI+15nAAAHr0lEQVRoge1aTW4cuRX+WMWuaqm75balsTwz9sDw/GACJDGQheckWfgCOYDv4VXWuYGBHCGr7IwgySQLY+wZe2zLP2lZUlvdXV1VJAOSxRaL/VgtIVnMQg8QxOL7f3w/rJIY5/x7AAyXcG5gjP377t27f3j8+PEJf/Dgwbe9Xo/HmJVSmiH6TIGmgVW0hqVwbi/Gcx4I5frPXTgKNtE/fPiwePXq1e+VUn/iL1684L4DlMOXAWw/9/v9o+FweA1AysuyLNI07cec0ntSyjWBMaf9AD
sayuBQZqj3ok75dL4Nvp7Qni75oZ8+P+e87Pf7td7mnHMmhDCIJEnWBPs4LcAZ5MDtUzy+TMcXe/bB1xHiKV2aJpTn01G6qD3HR+FCvWmawgTQdzYMTswpyrgYaDyVzX4AqDI7r3zN1+VDTLfbp/S7NUUf2tfZ/2JwUZ4u+q6y+n/YEsOH+/4zxUPtaeCxE45FnBoqXfShcqqHhcZ3ydoEMf5YAEIcFY8uOSaAsSGASLOnjKFOMMZD8VP6w2GFyAFQMrr2KB6KDkTph8CdkWFGhApjKe9w/tQLnaT4LhoAH9cVDOoAqL7q08QOmpIfwqoHxqYkiEkV
0uu1z0fRd/G39tMMKs2RVHMwJdb50gwiyZAupzR/oL9lWyOblTMkSq7hQ78p+SG0pjC8K4ifIXVdr9YOljufQ/ItJDrFG1q9ThdH4PNJZ5ZQ+hyUgzGqwT7yw6dIlx/X+MvtMarhPgZv/k7yU3vu2cnuf/hxdQAUvQ+U7z5Eh4iDWEkKvgWZDZB8fAfm9nU5Vwvy6rKpZFZ4oVZ3MdbwtfqnPMPHZET3hOWTUhjZ1CCLBYqaBRo4grSlBJA9sjGAT1+v06YcItsGq0uopAfZ3wHEEnw2WfHLNIfYGkMhQSoKk7mO3zjJEsjhPsBSpPNDJGLZssXvpV
q+zEY6QujNJ4A8y6g6GxpcIsoWT2yoyeDQqP7fCqBm8FOYCiCIoSF0DwkusSu63hDLa19aR0SJBAw1z8FZD9n0NVQ2xHLvK+Owpql6+0j5NnrHPxu5uiUUV74ArxemTWB7F/nkKVh5avD+5bm8ehtysIukPDW0df8qsskTQNQQw+uoxresDfpQ0p6xWQm5Zrdvf1cA1zJQ13hsilIn5AvVji72vm7h8vdPIPSh6Oa8mCKb/GD2xed3TVZq+VU2gipnyCfPAFmjunYH5WAP6YfntkQB9KZvwKdvgIRjceM3KIf76E2mkNp5l6X9K6i2r4EfvQT/+BaK
5yhu/BrY2jW85ehToJgamzRUe1+j3rqCWtvWvIHEAuiAuua1AmizSZmTSSJElBIpFYRUSBenLZzJaCMTSMrFWdmUBWS2bYxnxy+hv1+Ug10oxiETbgJn+5MyaxSnzXNppmaVDZCatmH7oJYjekOzZlWBWpew1lMv7ZofQyABX5yuWpRaziHyHWMfa8pYY7TfronptXBD8RzxsPfAJp1lxyU1TGPZNPPk6EXr1Kxx2hxlfs7eNWEc0rp0yVWffIWkXkJVJZD2TDZrWlPC0LLlmeMKtidKg7F4LSfhZl3s3vHs1AFeItX0hvqs3FVjE/Nkowne6jrnZx
/h+1oAtXDqc9WmANpGLFcTt3V5bSapEFKnpA246V2WvhpcB6oC/OBfUKKCGN+CGn9mZQnR8CrTt4wj+kCqwma3kKtBo5oMz1//w+B9O1W21bLBHK6Qa7JD/2JlHQNuy6T7SkAJdEOkyndauERWsIeirwr2umCD4IIqbF6YFiABN41dX2t+V4Nd8Nkh5PZV1Nk2ktnRSq6zmc0PIa98iuXoM/APz42eevc2kuVHJNO3pm1UW1eBkze21+YjE0wziLwh0jUkNsWDu4tiFxMlhClbruX1b5rSaAQWM7Cjl6s+w7zT15lk+tjRAeTeHRS3fmdwaWGna53v
mNYgm4wubn9ndS0XYO+eQujgNYdnDn0+Bd49Q7X7BepGFquWSI4PDD59+wTVjV+huPlbMDCjp1Z2gCBy/73oxwhOIcPXOOq1Lnn9z1WTpfD8h7/awDlFB9+f0Zz+B5h9APKhKT19x8vcxDs9RDr50chh+QiKJUiKkzPew+fIDp/b7NVOnhwgmx1C9Yfm6qIWJ0ansaOYgv/8N4urFmbYcNNHAUW8AoY+xILWCqCK3eW8dezSSe2FHwsoGvtcA1VzOSbedMx6fmz1E+XTotX9L+yBDq99a3AknpJH+BgDM0TCMvZfoGOfzB24l/EYPjSK+thAGRzSx+
RT8mIfN6gso4CyJ6afUzUfDhX/2WVreNn0HQ6ncthLN71/U8aH8mN4yoeYzRRQn79828NqNRkYS+uQedMeIiXSVS4XBYq3S1eMrgsuVMKInFCo9CLjfdMUP8+Uj8k6zz4l5yJyY+/ClFwelisFVJnHTp36HB/jCZ2NyexyPPa5jaL9X+yMgQ5gEvsycQmbQQ8R1hXhS4iCCZp+E5kLIfImhdci2VX/OGfPoSYxNaWp5y5ZMRtjt4AYfWyP0JsqZf9Qs7+//5Pe1v8b82ePjua+hFUcddu9efPms0ePHv1Fr/n9+/f/+P79+8FliDaDbnfj8Xh27969
V6PRaGG+fiml8l+64b8wMFmob3+MMfVfbeIAH6PWOzAAAAAASUVORK5CYII="
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap7 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap7.BeginInit()
$bitmap7.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64f)
$bitmap7.EndInit()
# Freeze() prevents memory leaks.
$bitmap6.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.EnabledDBG.source = $bitmap7

#DisableddDBG B64
$base64g = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap8 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap8.BeginInit()
$bitmap8.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64g)
$bitmap8.EndInit()
# Freeze() prevents memory leaks.
$bitmap8.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.DisableddDBG.source = $bitmap8

#SelectedEnabledDBG B64
$base64h = "iVBORw0KGgoAAAANSUhEUgAAAFYAAAAiCAYAAADF5S4gAAAEYUlEQVRoge2aT2gcVRzH35t5MxM3m938cTdN0gVLEjHuEnCTStM00GCtoTWuGElAqIdAzcF60Z4UxIPFQ4oXA4I9COrFYA45GEJFakCjSLJg3VxM4r+YmGygbbaZ3fk/8ht2wmRnpSWdR9NmPrDsvPm935t53/d73xmWxYFAYAb53DOGYUjBYPDK5ubmBELIxE1NTV/4st4zWNM0IZ/Ph0dGRl4cHR0VSVVV1cYDPqn9ANZ1ncUY66urqxGEkEgwxuZBV8UDTEKIwXFcIRgMMiA088
BPaR8BRcrzPIY78oWlhC8sJXxhKeELS4l9Lax+4lxcPf3GcVegCMT09r6YK3AXWLknzsVp3TtxndkD4vDHb5XLqpibHGevT6+4AneJ1vREXKusjXEIzZbLUA4/2cUjhPZyDcgl4o0VFqEFV9ADPBEWYKXtLJf59jvnOebvX7KujgcEz4TFuiKXqxzYqsah1hizvriiHUnGUUVliLm5/g939aOdKtR6z3fo0cearQXK/rlMrl2Zd46hdQ606M3JpKmpMn/9mx+ZxR/KL1hjIiQffeE4XANJYo6f+fQavvWvDCGjtTuqtD/bhQknsMvptCvXY6h7LIgK
205Onkkxhds5EAfatr8pZy+elI8kT+Ltm1kQA45LfVV7/FgXLIYZCEWl7qFBENB1ocZEKH/6tVfNypoI9DVCj8bkM28O2jHIg3yIwXiufI/xrGLBCzWH14J/CV++M263+czMNJmbWCLVDUL+pXcvGIHqMAuVrspKxW+z0+z3n1teZ74yGjFqDh12ji1MfTgOlcc1JjJi3+vn1URvglvL7PJdqFST4QRh6gOrL+4cyMrtp1JQ7WZtYxRigauffIbWMjlS3TAP9+CahIdQ81hcuC0741gRrfbO1iyKR37+al5/6vmEPHTJqi6DF8JsQdm11e0cEMWZuw
uwGLWQ055+ucN5GkTd6V/M3xmPItQ99k4oz11IWU/+jeV5qF6DfyR8h5SyQJ7JEsEpOuwaJn9rq+xCUMYzYfeKLSr/9WWr2o2hS/8rglndIMC35ccl4Hwua1bVxpz2A/2hOvWzFyOosjZmt10DU8AzYaFiSh868Cbg6lgqiKHKRrg+Zr89gNBgK84+curtPvJHekFtPZaENruSWS4dh/z164LcfqpFGngvxS3+lEahSEhuOdorpKcmob9a39whPzPSBzHr7YQynggLWw6V8T7YhvCBuNNzrXax6uChprZ190qdqUE4D9VrBmuiqFiZRBJzWFMkiMMi
WA+6ouXYW906nptYQghN2mOB33Jri2m7b0UoMg1CS52pFrgGu7WxhKXtLddkPAK3tbVdpr16BwVRFOv6+/vfHxsb+93/EYYSvrCU8IWlhC8sJXxhKeELSwlfWEr4wlLCF9ZjBEHQkS+st/A8Lw4PD9+AQUldXd36QzS3+wbP81JPT89sPB5XrL9xmqZZf0C18BqwgAJCSIJjEFZ4uOZ33zCK4hoIIfQfV2X1jh7icBkAAAAASUVORK5CYII="
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap9 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap9.BeginInit()
$bitmap9.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64h)
$bitmap9.EndInit()
# Freeze() prevents memory leaks.
$bitmap9.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.


#SelectedDisabledDBG B64
$base64i = "iVBORw0KGgoAAAANSUhEUgAAAFYAAAAiCAYAAADF5S4gAAAFE0lEQVRoge2aX0xbVRzHz/3HvW3Hn4F2jFEMWpaMdpB2aGBAgIxsZFlSEwxLjLwQfdMXjS/6rD4s+uIDUd9GYiIJD6gxzTKZxg1M7Fy2FI1SJrGEQddtFLrR294/5nvTO0tvddj2ukHuJ2kuPX9+55zv+Z3f71yAUlWV9PX17QuFQh8QQtoJISqxKAlJkuwsIYRaWlp6URCE5wRBWKEoSrbELY1kMtkAYWmbzVZDCFm12+0JQoiymxf1JJBOpx26sEomkxGz3mpROiqdNaHSNG0d//
LxUFiLMmMJaxKWsCZhCWsSlrAmsSuFlduGXEpLt9NQkVNPGrxVhooy2N4pbKkGdDCZjP90v/5dlTIit7YYYS5PzOtlUsewW2wbDPA3Lk6zoamIwcgOSXUERtj7d6P8wpXJQj1QX7H8yxy3Ep41VD6CR9neKWXzWNVWyUuOWhd+pu+tLlNSWkwdPj6UevncqFpzkNfKE6sbmDSeBgN7jLJ5rA5E5S58rHkK2zY0Dw+QXnjpGMqo2zcT7K8/zOGpt5d7Rj2KvaaafrCeoMMXI9T6LVGvg4ertQ1OKpMS2d/mFshKeNuGaMe2vsWFvrknIx9srOw741U5
gadXF6LMjWBUb5Jbx4UvhQ2di6TswuaCBTDeEzHpQLOHI2RWaWp3QmiBkElm/VYU3qxU8NXM1mYs09Dip5va/Pw3H01CXDHwzpBU5/LAw2VbpTP9zNEu+4VPz+viokxpPzlEyXIqLbQ62TqXi59+P5g/B4SoVPfZEUqWRK1tY2uXUPV0EBsBUcXTb47Iwj4nxtk6MeYxLKJITE9elJwWFc5mSCTwNiyoIvx9kP/i3Uk88V3xDrq1xCM4qvg/fv4OdRBUpTk+4x3w/m1XEoWvzp0XPn97AvEUm1Ao6SDu57Zl70TnRffzA9ocfGe8GFMITU9iHP7HqW
nDAorEVI/9N5j4shYOpMOdXXgykdmoIzT1od4FC0UoyJx843ghM3R6K6GHDRxv0tjapTS2uuiFK7Hcdoj7TGItgtNCmtoJvbW5IdW5eGysVHuokWRPlmYHfXtfMYxVDP+LsJSSEQ2FK+ENeIp0pLcLNwXSNkjgTfpxRpjQj6ih7z+AOLmtJnvlkqsPuOWOgNswL5bjC1sqHVOFxdGEx0AwQ2V20VoYqDnII8Eh/rE9o1GycXsDoiIUsJc+u4p20tj4WwYbeSCJbSvJxuPcDctFavZ7iKPWYKcclD3GKrbKKi1+9ox6xM7hALyV/+lLw31SftbnQiJD
OxxpXRSVEwSDAAOvHTP0R/Jq6XYiAWVaOv0oY25eM3g3woC8v96tvTRkY7t49r0R9GPvRLX2erjBXAwLKpKyeyySCD4QlLm3GtFEzbsmaQu+PDGPTI67LsEHk7l/N8pc+zoModkjvVGx2d8vNo/3M6lkDPaU/fWND/tvbcaQ7ZHU8F34fTZYaBz+20+C6VOvB7CJpCOglXFri1cxhj4HnJT02HiXPo5hUUWAPyZyPp/v1WQyeZTjuAdlVXknNHir5Kcaq7VklieM5pG2Sj733pkLvA5JqVDffHRb9J/XY7l35Z2M81+Jx+PNj1/YPQiEtX67ZRKWsC
ZhCWsSlrAmYQlrDpQlrElowtK0pW+5gaKq0+lcVBSF2ltLe3zQNK3gBYEhhDiGh4dPxeNxl6IolvuWSDwePwRh4akcIcSGV2sE3l29qieAmZkZm/aPx1kxmWxosIQtFULIX9w3ZWODumCOAAAAAElFTkSuQmCC"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap10 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap10.BeginInit()
$bitmap10.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64i)
$bitmap10.EndInit()
# Freeze() prevents memory leaks.
$bitmap10.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.

#RCNote B64
$base64j = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap11 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap11.BeginInit()
$bitmap11.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64j)
$bitmap11.EndInit()
# Freeze() prevents memory leaks.
$bitmap11.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.
$syncHash.RCNote.source = $bitmap11

#RunActive B64
$base64k = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap12 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap12.BeginInit()
$bitmap12.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64k)
$bitmap12.EndInit()
# Freeze() prevents memory leaks.
$bitmap11.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.


#ViewActive B64
$base64l = "iVBORw0KGgoAAAANSUhEUgAAAS8AAAA1CAYAAAAQ5G2RAAAgAElEQVR4nO19aaxtyVVeVe197thv7rnb7Xa7u+0e8IRxGGzAJGIIEIQJMUSMikIIihL+RcmPBClSZBEBgh+JQ6RECUKQBCFBYoNxgoOQHcA22HS728Z2u91+Pb/3ut99747n7FpR7VrfWl/VvY7yN6a3/fqes88ealjDt4ZaFUUkhhDKv1eOV45XjleO/2+OURv6ivB65fhKP+SVGf7KOsa/TJ195fhLebwitL5Cj/SXfQBeOb6ij1cE11fwMT708x94+yTyL4sUy9RP/o7PD2wG+Ws35hBjDCmGIC1pzF+HWCkmSzkh8+cUnYhwj
54v3+dTkSgNn4Xs2XJteWb085L1dzpX/kp/ffBnS+woWn8X7ntpUOz6l6K/I4s/MukD9Fy5r3Tb3x/tecfGoG3ayQePAQ3dSXb+Sc9p3ik+LoL7o7ZTumeKzrvUuZeB5oReNJ8vx+SaUPp5xLlI4xdp3DBGfduyP0dwDdpVvk91fiXp59DRQOzGD3OEuQn63BCae8vDBTTA8x07msI5fjfoAYOQT5gbviS28zufw7tLPyep/cMDME4rakckuuOXSfCxpHFwmujaEk7gPTQS72UeonkUpp1yfoj1Vp7rmWfFGwDklLu5yuAt+s3fIbhuf0whnFlKeFOmTpWbVid8Xk9Bbttq2YY6KWihXxH5Mr+HCD
afMMAQglnaCcagpqh9IIJmRuFJzTQzECCYCBBd6s7n2q55AkCskWYZBMmwlSZfiOlsMlN0wkw0hNxHetYxYmdmxfeTlEcjJDoioM/W3+DPatqBNto7nQBNCORurNH2E+bTWtoxh8SWQG0oc3v9MYEWvJ9S2piINkpfMgnfSG1lmijzO9W/tZ8urISVFeaJBZ2NOY2hjmk3LTr3NAhC9MB9CaGlkZOUpCkDFgKxPWcgQnzcWRHYc+Q4z9AzhRTy3L5J2r4kas+xkenIE3227/QTfvcxrA1vz7kC03btjsaI0ZjMiLNvTPktzj3xWQSqgJQmqT83lqU0DmOEGGQQMe2f/N7KSJG0rDZUkZ1gtkFkQgM
bSYAmmiNMaoimHYwxYhdzHfWegYhY2zQLrYHGSQh1xI5peOzmPuqFSgyC5ydCrKljcrTzmBByjSx4JzNTIiUx0rVRPwzJCWTC2NA8lluG2FKmELOcILwbZDv641zoiCsmzBNpWGOYFKBgRHise4aR0My3MTozB+iatXsi+mnQQfQ+YyxBx4lQKhiRkHVVRN17yuUTC7fggguCNFHb7Zl0Hf8zGkB7xekZg2PPTS3aDOGYwqrvjn5fUBQNImXg0IxhbManRWL0tzcbMBcQrPbcRuNF56EI9CnOD7VfYg77WduUV3WCi7V3fVjyhseqvWwsiWiM+boOmqBQ5NQAztiiBH5OGuyU6RMmnADNSL9Bc2ln
G1M3UrsZVc2MPigTSYskUwO5yYYNjgJZO2cya0SJiajamJeZG8IR8ziQSSbUlqyN4HE3AaanEpRGdLQ4v5PsKv3cCqk6D6Y5ExEmkAWby/NYsnJC+2kszESo7bHrM4hXz0CgmpCOlYNTanjBEYU4ymDUPEajaWYCtM+uHaIjv9yhhRGKkjoFM4mEDsb/mKAHCue5MRMdgoE71dEu6DkRY+fORMO7TWDHti8xuoAUmN9E9yZEmHd5jr29gs8pGf+7AqGxqX/F+mQ8IK3SOAF1mwwQ1bLSdTTOiLCeHxsTRjs5qk3dw8FCSDElE1QMQdnHBM1sGo8YG4MVdQAwaJEkspkirakiLJ3RhkS/AamBCCC0M
KkuZY8jTOqTIaSOENmvZRqJ0ULkvp7gT6EPs7CDHymSP4E0doC8HkNLJJkgOLeL+mWoYHAhaodY+6VhBiiOsUOVTOisCLgd5fwkPi696UuIZz4/EgLGuEBQl3eNYDZiQEVpMnXzPzNHF3qK2qZANudabaNgoMdECEcc7UVS2rAoRqV36YQMeKQwVKTrTUAR6oMviHmG5RajsxFmJTEzIzFG9Wxi4xGmAMUQtSkzmMmz2RxapT7r72gKAbQijDNiFWDmUqGJNuQdy/9IRgR6T2STtEdLbIWpjZBU16UkNigznWaaNGgtnMskyGbiiTEMKVXIptzGaG++J9vcVILODSqzgbHeqlAbmTk6pgRst5e1Qq
0KLYaxqWWsQAPcmxcd0pvfMyqzDK0zUQa6uRJ4/TS0zDWbc6G7xn1NmFon+KGOpSkzkZYQTRh3AqPR4KAEZRaMB6GkE3xRUTWiVISjhFJYLqr6HcChounMhI4KDWTCKqQIrR2E3gSNZmUGhQXUMqpvpfedmVle6IfoPWv7o7bT3QgipU+ZmGOC0ohR/V7zfeXSeQ6g0Y1WYj3HaCUQMko07+Xa6G21l0J5lLmJrQ8nQIkFQnES3CMN2mSUE9zdEQwgtOBByJcLE9AFpk7EkDywRDxjApud7BgTcUEsQPSkbGv/aIxAB+J9CwqkrR1ROwYUNiuwCkcl6fBkWCgS5xkSRXaz2cgCy4gitAd8JmWSRjZ
+A5lWZVBYMs0Iy6cdXDhPfnbiZaGQxTX/2LrXKgHqeZ4gaBJGkbivMnxlzk5LoOkmSAYN2UTY3OW+oMSuz5jE6C0sYrLro/4+P1PEiDta39HPaL/NzEXtroI4EvM4oeNcj3AC+eVEJRSELmttEAebpP6MSMSpQiDEOsZGxNHMx0DElxQOdEx5rP39eIeT5gJM28E2tDl2/in81jm4TchLaBi9aRORpV0zWF+DCbeqrIWFuFkXoKnybwXa5ndB+eGdmHOVMp0PrbFcbL4JKTM6i9RvIcGUFVHymHaKe34eAlaMIgeiQ1HriOeK53Ho/GmzqY/xDIEzDezI1G4GI4wSQaPVDxsVEMDP4LwmnKQ60oNW
VUBI+avmo/6NdYRsMlyzCQTXHOkR16zKrFEZGQMwjuRzIH8V4OqXS0CDqdWH5UeGvlkasypKtIHUDI7WQVgFVL1e00AmMW0q6GuF8wwvgiRTMdGZRUPtbBpkRiKkPRl1WFsIOWZpHeuwK+2tBRlXdCuEzByVkn9nJO18khCxYEhwZu5TGQIxkvla6Hc5IVUEARcoKyNm1fTmU0venE5nOYLr0G9UNB9aRpFGkaGtLDBJsPOhjKuINBoNA22MbZjQPi38vITgCjNJAz50fh1p85zxdaR0PKDkjD9L0M5skxBaq8avc99RQZpmhgaDSurjqpPHAaKVCsNCY+PQRjApIj2b7SkwiIjmAoGyTZgXUr6cf
gJhNOXKi+W9VdDPkRBBQ0XnxoT0ikzF8hIILTarivZZpOTMPCOTCO1iqqecswjEjFDcgcgoy2xxIj5oF2KshpgbmNoRniWCkORz29pD45DjSRFggdDlLzQXTBNA+GNmA/xsgSJDrt7mewZql/o+zB+A3xgFJfo+qTBvAC4oGcLOI1yzcEuEPi3CmDysPQDFdn4KFnINg0DDU46akHJRGW0O9RCD5RpNqiHHGSVKbfPgyG6qplg1w+GS0BYlDV0boq2CwMYu8TkgZRqeQAiTzRUgLRpjM+U6gWb0Bn+s+cSaMLL4ddJG3YGgq1mpfhti0j5lR6O/wsiP6S13igsXxVaAGK9yriWiiUPHQEJtxBwERd
LMN4jODxxO7xRb7N7NtK19t8CFBV+EBDdQvMqdhHB4rO3JovBDJblalTKyeZhp8k865slRLCkauqDBb8P9DYSsUjzSQHH0aUFO4FVuwrAmIFiC4zybW4GIt2dC80FER5grMDWctqmz9RH1o0jeRP6MGFvhE8mhG2LrLwsUDRronlm7iXvXdU6qZmYzRH+o5mylPgiO2aQZalhm1lR636CzDeRT/WuV1XAf2p2aWKEhA2NQDkgEStaE4IJgEvUPjWT6FkRLkVT87nxoQZZ5AMVNCmiiMtfRxtQUl5r2GDcR8h9JY0ofy/srV4+gj+Q0hGgcrleFIOa4jjQGhA0h/KXzK+H5hjKIvoxf9BoI2MipCh0
9m+UQXHBZFJnGMgDRJx8PvtefWX1+s7LRMTbhKmJujTK08zyqJjQfLweNaMpEWnMZfEiIXa0LMbdDUvt/CHCdiEaQReVGrEg4ZMmltaJILdWIxZwqcVKWvTrtK8EMqbFLRdpOGOqgUHVgYeUCbSbWBZkMMywfHZq6VhGbhHASQpDjggzUOqrJwja6kJmcpQ1xJ4FwOK4BAWtFYL6qn8tc6m6fR6AWJjYiTKQySOeLkwhNHQlBFIGT/E6b4Eqgot9BvEAkZF8a0xf0PM8jtCVpvs6/KFmiBTUYqUGYmza2IFA0Jmsssm6lg4QW0auSaOYcggcTwA7kPsrFvqNAkWIh5u8VnLTvagIXk1kUogJL0Ug4
HlHE81lAhmD5fDWjnBWFzq8olyvzCkzyikA8kMBHFzBXeqU+qhDKM70E87filRBwPnZRYqCgDJmpA5RpfU61JlI0BRKIR22VBWI6sVXckQa9KDrMH94bIStSDOb0V6xtg1Uj4yHN/8vzQ0dmqC+HuJrzsb6gvKiGWcUa0yTPheMCgwceQkeYMEnDhIY43bEtpLEA483cUzvZ/E16/2KoArAMflSSxuBS2FgjS44aIHQs6sRaoYq46tfofi+/TFmMuQOZCIw4Y2j7A2KZsqM3YUICYTSM4wIjK4EJnYc5UeE3CeMYG+2YaA4YaYFbkvoxm3awn4n6hlMYVw4osOU1BBpzZdQcwHSKIFM7trNg4Xw38
XbMz6X5B1OZkEQOWafsQAOQQsZUitkM/UtsUzuMKUWjZv6XTGkyf1u6mhUXnOfZfYoingEbaTxjON52hv9JJ2xQfglqFQ2NuCNLQo7PG9xFoVcKsb1/TB40MzQVa+BiiK2FEQmg8DO4LRirIUid49nP5vi2jn+VNVnqKDdmI9IiOD1ijLTuTyONk05qNY2iwHHGzGHMYAzhZhDCt5G0unWSEgB53dxIgzdBUauTIZmZhAd7xCMq3B2hCnU4knKLqFO1PGsQizrOvwHxzbRc47V2AppjlQUa1QgGWq9BMq2mFmS/z45ssvnJNLE7hcaOkGCzTAi8B8TBSYGW+9VFH3kJVudkb9wr9rbZlG7bgiFNHX
1LMARhDD7AVmHkUZGgBRCSC11D7aPmFpaxhmDhqKc1hQIEgRAa6LG6PRpMaD4adnRPhPCZjjNWmVA0cnYJJJiuxmrmJqDoqLA/UoUrQ3ZHi/ROJh+g5OzPtWCMmXwpyJQ9dUQji5Iz0J+hLIhIE5QzMleEA4KajbUu0hq7sVUBJJg/sjTq6gJSLgPRaaRxhWCKygx5TnWRKqjK36x4LCKqL21JHI4sIncEnzGY5eG0pMWXmsQqdYgIhKWtMXPJEUNolRwVMMGScYSYFlZUJID0A+zzunxkhuKA+uT6mPEyJqxb6yY4F42RQGCOSBApDRVFWqJeJOIv72bHOcLPSa/nhEpA8kwpDzBxBk36q0jArCV
FDW6+rbp1cezU5yUXOEZ9LofBLbRthCk6nlFjRCAsTx2Zl+kUxZXdJzapWB3ITHX/WnApWOfAfEJuZrkJlYjZgjqTuUN6TdNvMA1rftAeEK25OMjCSLFBMMLXaOdnZo/EYC6QHS2kFNuAiMkZMmEjBbOY2aP74qZZuUbz2wmh8nLvlJVhfa7NzAVSnE226FF/nTsfLwhYB4shpuiKjdZFQmhlCpoEt0AEjsEUDJTYfwab9/qDgS3wNfUPU5yIR4MGcyDE5kRqQVJsXbRakWr0PK+xE1ShMorgd9YkcxsUzlsmLsHvcZb+oYH3E0liDNSjV6a1T1ye1j57PY/PH0o6khBuXMR891aaHj6Xjt5603h4
alH9cTCdktnx9TE4P5ppabChScKjfBpf/+iMFUIXxgVvpRiNyIx4jUrF/G+mDdTbeUy4dPk24j4jW2mPZ2UVAryeMTqz1nFXCUZJos4gFI0M6tyfFLUQf5BCccME6RnG4NXcFEShxsHMT0sTCUR8or5RY8BofD8fHKXCLxZtIoQYlLl07AxhmDDh1Gya5ym3607ZUukDLGlOByoaPJppaZn1pHRnH1KImrwsoEEBjcC4hGzNinwcsLgyCjXIJSDCaiLVsHAOnpdVxttyDcs9iSKrEDQxeo4azUNwodJAaDMDWYFRCowpenFfLAt6RFExiEImMdEduIqWeLV/OT0q63Mq+JFZrrjC18/q/sPCUR3PZ
m0jLwuqORnU+KDZsEmlegAqoIy6OtD1HQlee2gvJH+KhMdfWi1+9Ynl9lP7+Vg616WlpEtXp/Sxq9Piv35pufU37ljsf+ur1vaapZCKebvseNjm7iAM8CG0KQRYSpL8mjlVAr8N1rnYlMoZ2vc1EafoJqkgoVPsvASkIrRRKgG8dl+hCtLJ/DytaT33j0zSSIyUWMCBkHTQ1gZFn+I5NJh3CFGESgc3833xNFZgcOSIpPEEsxeR42S+jjk6xImmOJ/IRE5YuiOuPXAdm0+YflYyZApSSgWYvCJ2RtjOY1GVnplPQvOliAYKXFxx6rOyy9lmcWdJbIVfNNUJs7YiYx7mtEVsC4rLZOIqjYmhWSMSAQ
LjFReTonPMCwIDNLHuuQCdaOIAhIWlRKXj1TZEl2BBFiCSROzvEed2TtzFQP5JC+R5HqAMZlJ4M5FvV6Q6FmQDmSPaOB/srMNAB0ptEDUbYUoMXXY1HK/Q0hwsAWx/35NHm//l4nIz/D8cu1OIv/bUcutTL02Ln3p469rmINlSHdTm4yUXBPHN1wOBh3Zi8PqcKIvaUQRuIviOF8yOTlXrPapjxrHEPIMJjUHrZim1WZwHVaPpPRGMUx3CEzFNalAWaUSMQ2h8JE3AYKRxs9B+9DZHJt5OQ5v/pV8h0C2uRvJiCF4ZpDKDN9rGPHbOJ30oKyM3p8WYP3QCRExJFLRZM+QDcsIUzWXqc0DQRTkz6v/
EZi7CNJufZ77QTnk1tEJhB6ErY/AJx/IXlJziAA+PazciDb2Y+8EBEZScIyxNDocZzYJ06HLA8JyRgghCYV/4FDPZfqxEclNVQQMY0K8xMmAwPipuIKROiC1J80CgQzpk8kIxUEcChblzdz6481IAiXOTlwAkG50oFF1otrG8/8nD/6vgSv0s6fHn1/LiFx/ZO73MIZZgQfk3Rw417F8haj2XzMkQVbvV34I6hlc5xH/zyMG5X3704NyTV/Ma/47n/PFzy+1//ejB+d/8/OHZ8ow/fna5/Xc+snvb/352uR3n9IQoeHYI3g7kH4FwEyDwbE9EiwQCATQ5SG6CedpziOGTL6y2f/lTRze/78mjs2Ut
IqJt5qSNnqQqzAARcE/nLjmHwecG4WJO4mha1gQ9fDnRlYEkTiwOBmPmwA00rjm2swsJ07hSzX0MhiJQLaskRjfsS0FUF9G72YnvOV5zf4tgqcIpWiAAa3LN9DLkEudrbdA1Rw3zadAnRI9229KuKHjHMDPk/DRJRHf6P4kq+HJofU4p+KBXT+OcjGn/Zv+ewMqJKqTruWQ0hgTOaJMLJE7TDcEyD5PNEVwovpYULOA61umLXAQqcIwHnMfB9inBJ13HuFo0gPeVH/QZdQ4jFWgwv14kdIY+a8BFzWXzeQXke0ljThny8uhGzX+paCW5xiP00acWlEsev7Ja/OcvtYKrSPfvuHVx8LW3Lg5v3x6mR
Qzy4v40/PmV1eK/XVxuXjryklGPX8/jbzxxuP0D925cHyga1oFFc05Li4g08zuE9SHK1hjk9y9P6zduLKe7zgyHvdD8wDPLrScPZPiJC2s75ean93JJRwtP7+ZFtsG0aGZdjqT2MqOUupwkiacD1MiZfqdaZ9JEY5lhrxzK+NGdaQNeDRAMoDxQBECL/iaZCIGQqUXQkNYyqVc3dWtEUWsMh5qMje9KAw7u4INNF10gOjF6UASX5oA1p/4i+DAR7o8RAQGgAHX8lzGEi4Mc+YMi0+x+5WNmnV3sfjVfMkZO8cBIVJW/kNkMoZA0/CatMLdrYFKLL9C3lSxc62usC6m9MkOLOOf/D4kRo0eKI7cb/i
YKrDF96/y7v9bATYVTGbaZLouayHEGITJp9HhyM7/mh1GSn6F/849HDXFqgEhTHix6aat2DDhatIN9xrZsKbBpQeVQbLmASwiNhmFRaTJ6LZpjqvjFkvww5oCSv/L5w20ewBsXUf7RQ5s7rzk9rNDo8vybtofpW7aG1dffsnbw3sf2T3/86rTAPb/73GrjHbfl/btODStOsIwVKkomVEKDZ3Y5/r3tlsV+EV4fvjytf9+9RNAxhBd3p0URXOXcg+fHg3L+++/bePltN097rz4zHGar5FhvyFVwCRAEIidYeALfFZhypakY4AKsgcuNz4XNdCa6RmprdIkkAhFNCsdMBOFzbqo5odv54EmTeOiQnAE
K3J+kc4xHRtvtOkuUXwFFRtKOmZgLZmViH0umyhWiWd4NI1bBZdUfzJrxfKvobbOgTHa3gaBIQPBxsTWbLPMCIVstJSPmA4yOrGAamkyn+liT0khTcsf9qc44Humz+lXJFZcZcrMACZ7eE2Yz1OSDr4H0JFxLnI1qKs9ICGMSzCSekdVKpFEu7oOMGhmvEUhkFiAyOlqVDp+DbOLRFQpXmcjZ6Y+Vspr984Ng7qdISeOg+xURozNqf0RzYEaN2DiXRQyoIEv5kcvLNXbOFwH50w9v7tx9alhhotzfUxu+sYjykw9t7rznk3tnP7+bbang7z99tPWjr9vcMeLQAm3VZmZtDSeg2+7QCQ9eGA/OjTG/
tJL0mZdWG68rQqqSnXzs+eVGueqdF4aDsxtpKgP3xEvT2pPXprXyviLAwGjXD/Pwh88ebX/puiy2F0EePjfsv/mWtb3yqMcuLzef2c2Lhy6M+7dspWV5zgt7eXz08mrrLTePu+c20tz3L16d1p+4Om3ccSod3ndu3AeR567qnE1Dt5B9htAqiF4+zMNHnl2eubgra9tjyA+dG3bfcPN4jX0cZRIev7za/uiL0w17k6T7Tw0HD5wfdh+7Mm2fW4/LN9487pT5OVhJ+vAzq7OfvTbNaPnO7XT4zXcsLq8PIZOfyctDUxTI1rfResrMPsaupDClo1QHv373yiGejuI5R9XC0XWS5kOclCog1JMLWPuv0
LuCCZ865im64HX/ThtcwIoNJACjf6GruApXzZBqjtq8mBiIkho0BC9wAKU1Ro/WmZCD4FZzFUJ7sOTdqPwVlU7cdxrIP1jegGU50ime2URVIRRc0DYmKJeJEgTyLITt6UwEyMUEXRBc6/sSCF0HzazPnRA4orFQQSeWYY/IIhrHQgvRMF902dpZg7o13U8mdq5c+6eXlmt8/bffOh7edUNFXFzEbXACmhtfTLy/fc/69X/xyP4Z3PtHl6e1H25Cw11goKviwEQIIVac/d9wYTj878+vNj91ebVehBe0y0evTLPwesMs0OqEP3ltWv9PTy1v+OG7wrW7zwyH5fyLe3nxs48eXCgCEO/+0OVp4zuv5f
Xvfe36S0WQ/OqXlqfftZL0na9Zf7k85w+fWZ56/wur7f2VxO+6Z+Pl8sZPXVlt/uazq1P/4N61y0wg/WGIjKK/Ejy0/ukrq62f+8zhzXzb/7oybT3w3OrMT79h4yIa+fHnV6fe+8TRTbjm4zt58+zzqzMvryR99em0/+Zbxp29paR//omDu1+mvpXr/uDF6fQ/fnj9qfObcZmd4OqcY9UFzCdqJ+hmktYfDyZOHRFTBMojbVz+BTl1E9pQpSACGUxXraAgfyO1o6ehk/S1EJpHO5iZCT01KyCEECXGgKO1QNMRy5H0uhWVcYLABgpJ+jv3dTCU5PMSLchQz046kLZmUS2VQKkVuI7pbaD+BxsDfSa
UBClHIQVTF9qLZfmnbv559QXmAgoFiimQkGX3VMLCzkwPBOMnZOfqs6EJpwDnZoW0U+f9Fwsj1wn5zLXcJMN+3a1rB+YzaonF5b928r5z4/KWdV9yuTtJfG53GkmbNpo+nECobkpWKV6+v+HCOCOoR65Oa1ii99yem4yvuzAe0uMak6m0+99++uB8EVx/9zWLq//h7Tc8/Ytv3Xru7o04ve/51dZTV6e1e87W51/ckwXQxiNXp/Vy7mNXKpopk/PpnTyfu/v0cIi3UMa0mxF6fpUdBcCfdZAl/fvPH91YrvvxuxeX/93XbX/h596y+aUHttPR47t57UNPLc+V3w4mSb/+1PJC+fxjr15ceu/Xbn3+
PW/e+OJt63HJBPVHz67OFsH1jnPD7i++dfOJn//qzc+//dxwvZz7/YvL84GsIvbXiSAfpx33MmTkS8NcSYo8N34ukPLEewhBIVgk8MHCTFM/r5OTL5ZvqtpqFRGFaKT5ySrn64Vy7WguLCUHFTuw3IZN90QrLow+sdgb5l2NvpqVKu7bbNyJgczkAQGM7pzNI5mloLWoi/XhXlE/rLAQw6oBKG5Pj5lXDXjOo7gGbZWEeDRQo8pIoSAaE4AVEuzCNK1jIFzYkUzKShOBHPaZ8jBAdCAYJxyzwy1vKQUP+6v2E0NnEsILB20+1x03DBNF11qp7hNsUve122nF9790kFPqiCsSIUYiEJsJvVBrX4WCt
oqwKcLqmd1pIdWcmlHXd94y7m+Okcsg2f1lQp/ayevlvoduSMuvu33tenneqfU0veOmca9c9oWdaf3WrWF513pc/cnVab28/5nr0/ilQxnPjjE/dSjjlYNpTqp+bDevlevObqQVOWhNYBKkNkYgZpsveuzSarMI0ge309E33La2E2p7Vt9+x/hS+fzhS6tThbEevzxtFwH0wHY6/NrbFlfL/cV8fePZYQ9dNGd+CGFzDNNiCNPWIubvvntx6Z88uH7x7bctXuIhTYj4Isydjs2hLakRj0IKkiU5pUROoIWJ6G9AKTkwP4XNeQ8DmjbLiQKTheCIDozCyEs6V4l0ycsCnxPNwVShlyRaJmXZQvS8bI
/0QETW4AJXccXwRQgdIDi9DmiHz2jVDVgAACAASURBVGUleF6CNfFWRqpZIGiKEkZZIRvfGs2dI8G2vlOF4/zezMK1lQ2e72XZ/UCUgkAIqlK0aN0TZzH3Gbl41E+lFSs5lIWKETYJn2KVJuw3dMTtaM3wNstdSFx5Ul8h7iM2QaPW59bJylSSFiYemySlPwtyFmN4IFjKgI6+Lsycv8xAk3OEsAb/mvPDwZPPrLb/9Pnlxl+/Zzj6sysVGT18fjzAMxq/n07C515ezWbwMwcyvPfRgxsxds8dVN/cxb28KM17+Mxw+NQLq/HJq9PaEzvVHP2J+9au/Ozjhzd+5sq0edtWRXlvPT/sRydcdwJ32h4
8JsGqjs6T+dLBXJwjvOncsGfZ+CLy4IVxN4SjUIRm6feVg5qU/LrT6SBSzlfnUgtvuWW49oHnV2d/78Xp9OM7B5uvP5327z017L/u/HBtY4yWm4zxNcQVfNVC7saa+ucbYRDsRiTzeOSMGomIp6U1AFbJiRug4HfPVaqncA1l+guPMwueSAvlJ/jIqOhAZ3Fa0igcy8HBwPG+0BIc8mEJd4LLcAcLBtVHoc4ZHPk416A1658vfrelSMELFugzrd5d8OfaGkgaY1MenCuJ1R8pIl2pcnkmgSVdNBXjJc3cYzVBFe6D14Dz/SpBv2yvBloOxN9zJ9y4Nng7K/4H19y45mZfaezl/TzwADc+K3oe8k+e
PbC9Tedjc+EF3pBcyr4NRwVtqN5qd+n5t9yymIVU8XO9vJ+HR67nRXHkzw58KmPLfoQaTQnNgc7dupGmt50ZDs+txalcfe+Z4aicf3Jn2vjES9Pmgzek5QPnF/uvWo+rj7y42v7cThWW95wZDvh57ANqxgmfCR05lfpHmHFfrkrIRoo50pzyO8r3M2tp+TNv3vjC99w2vrw9xPzBF6fT/+aJo1t+5hMH9zx7vbYZCYYsZDnXLDamThvNS+SXjLEVOL3pz3MK6SaqwMy3xMyh/qMQvNS43d/RGVZadAFMOyyypV70IR5TJs4r5LowCyAyInEfTvUP+0JpXi9ptfC7RgnNbaIoNVdBCXr/EDk+GMJKI
ROEHPySoO8pt+9yZNSeH3zJE5mFUCqOCCcRh6bSkKf7C2mjDSG6CJ73R/7rNlEZgZKmDDRVU5U+2z64bS+h5RdES4AarRZShbU5vGYrTZeOJlP0n7y8XPuWO9f3Q/DnkcbjfCMpgu4vruemnXfckJaYbAgu1ggxMjKwxzfwvfx8y9awhOn4Py4enSq/ff2FQX1dVHaWBq0k551br2bs7Rtx+smHNy7RtFu6Rnnv6y8M++Gz4dwfvLDaKqbiu24br5Xfv+b8sF+c9CJh9n0hCAA+MscLS2JCXOLafL6smHfl96f3StKtVi6NITx7Pc8IsZiq5dpz6tv63LVp46+GBVDQsbWbX9iZNsr133T74vJ3vD
rm/ZWk9z95dNMHL02n/+fTqws//PrhGRsb1fSZaqfDWuF2Dl433XqUvNaaKSMy34QVkzD66JgB89+OlO8oRH4UXtgJISO9YEV0MfTogFwZekNd0kMKkhEW7Z2AhRLqcK/R+EDAAakSvpbVhJKhKxJc5pmitYzifbXKDuLfq1cN89X5m41JKCgnMDtNQCltob+WLtOsCLGadpY/GJ2mfSmSlwASfOcJhN+XFI/v6YnAHpi5qeMTTv6cCTZnMhUzkQ5HIpE6+Mbz4xG37LcvLjd2l9KDLmuoMtR8wW892eaHPXRqWI6a4MkmneWLEGXDqZ9iN4hOtPKtty92y0Xve341C5K3377YRekU9jdhXIqWukf
TJT51PS8+8cJyS/WLXD2Yxt/83OG5wuzlFRtDnAraKoKrXP+Wm+u7vurCOAvu4u/6mtPDwboiIYwtR1zYdGIfDUyd8u/B89XX9gdXpq3nrucFmPGDF6uj/m3n0m7Js3r1mTS/92M7efPZ63kd5aaf3qtBg6AE+YGLywvvefzwzk9eWp0uLy+m4mtOp/kdJb0iIJ8vOz4YSJjy+Is76oWFAqZ8oCTX7LnOAsEmpoGpnpgvMFdBEznAZCYR+ZQbs5Tfj3nO0pbCCZ2QBG0WpsnEbBCeE5mTuHeg5TCMCKEk2FWzImESO5qjVSrH2tQnOGdCTGL3eQJopAXXom0caFJ6xA8fKBaHMPIKKgOAD+Djwhmv
xGruSUeoyc81AROtHiNU3gCgiy2ggIXZZB5Kb2pw9r20Ut2lrLjNJpqRp4M2v/QtNy8Ot794tLWrhcBK5vwvP7Z/6u8/vLmzMcaGeBPVKPq9pw63PvTiap3b887bF/sgEEJcNvBIdtN6S1aWhipezBE7aI+SiBqeODpd7i8o7Nbt4cgckKTZjOhiDDeshekf3rf+0i999vDcL3326NxDz65uKObVn2g08aHzw8EDF4pAieH1p9LBY9fzojjlb78hHZU23HV6sDyz+8+kQ/i7U1e8kVO9Spb9Rz+ye3c3PeGfPrjxbDE7f/DOxcu/dnF59p89cnBnSXl44VAWCBB8191rl8rzLmyk1ffcNl79rWdXZ
+i6EkhY0CPlG28dX/74ztHmf/zi8qY/ujSd3h7C9Kc7uQjp8I5bxpcDaXo46SG4MiVkYuwjLScSF9ANssU8igttI1ShVQCiDJPmuthiaAZjyP4U95G10UrGs5yuEWgDCTaLTJhSBQyJHnSgXdjrAn9azch7ivbISSg3y5YyqfAB8MgaVZxUEHn0tdl2ziwLy3BX31lNKK55XSWZmquLoC2ep+XjyGZrpPFkfmP/tI2tsCOw/sd8b67M2oYHRbH2LNvJSxp3lcqhFXI5b/m2H7o/S3gXykAPvT8FjtcQwl1bY3jTTet1eUwgWEt+IUWHhIRi0dxhyFJSBYxJnj2U4dHLq/VbNtJ002ZqnMBX9vPw65
87OPVbz7TLiR46lZbf/9qN69xpTnjjvK6slUxzaH16bM7EiipkdZjHs0OUb7h53LvzVFoGrtoQo7xUHPGrkO47Oxzetj0sy5KSW7fT8v7ttLx6IIuCwJ4+lPGdF4b9H7ln/eX7zo/7cEqfWkvTtX1ZvOXCsH/3qeEQgnfIEjdCLEjv2qnZRxasJAqr3p3DPMoqpNvX0wr/7qC/X3Vh2NtepKmgqiIgn9vL65/ek/Uy7t94Ybj+Y/evPb+1SBOo/t4zw15aSXr+QNa+sC9r922no3u30tFTB7J2+3pcvfnGYefCZjp6w5lh/9KurH9mL68/eyiL12+lwx+6e/HCgzeO1+H3YwsKKNeETqvMT/ZrUYA
GSaPsTGcU5f6zilGzCUGnQ34mMxg+mxnZoj87OMhATn4TnNmVYFPUUJEUbaQKgVR30gpUZbWW13H/VoDOp3YgTQKfbSciFXAD5W9BwUXqFxSIj+2cSW9CL/j4Wz237KjI3ssoHzKBn4uNMmzPT1qmxQCXU1ykE3oKOLo5JqRs3ysYsnp5ISzjgz/3u981ZfkVtKt33HM73n7jevjxB89QdUwNo1Kt6QhzkjRrVLP0Fz65d+aTO1OT81WOksd191ZarQ9BntuX4S9287FryvGm08PyzTcOh994+/peaplBaPBnwQVmYm3OhCbGVS7c2qLhJo6F70cPEWlCdATaEsslbLIs4c4ztzv5ZPZ96CJjHKbH
fNiSFEYX8PEwweize1OkJKCWUxuLaqqW3973haMbf/u51dkfuGNx5Z13LS7XEtbRfVcn1A9D31e53QSV5ws+NaAz9AvESeYCCNkLO9oKCkd4wU3/xi1ooD+aZnehmoPwO2JohSSere1y4Qs/DylGi5LSGlpK9ZjvhVCJyLXipWoKI6dOobIAytRl/GfwJXfHUBfSGNSMn+dpNWXtXx0Z3VzDHuvjHpt0jGiKQWwyI/pLrgEbN1r6ozyg7YNwU5RJfmhzDVCVi6S+QzwVvMXmb21jXYe0qsm2u1iY3RAdIig4y5/xu46NZI7scuG9bgFr6fhPPbS58wuP7p3+dJe0WgoRPn84NVn4Jx2f2JkW5d8Le
3l49/2b10CjWK4BQoy0Y5AJBv/NBB00wUrXdyHb2ZzuKI8SGyYxZGzCKQUL72az2TG9rQ8jQBOKb7XPzAaTJJAZBY0Qe1QgSEnxraWiz4/NWCLT+Tc+f3Tzi4cyfvOt49Uz63H5xZ28WQRXue7Vp9Me+/kwz4m42vZabNYRtjsjs2M1MAKg/EHwFjvtJ363iixG9KmrDorD0gC0PVM2887Lart0NbqgyKYFGIQQH8Y0eba/ROofKxMuS8M1yJCsLbDkIJxUUEgXQYy0AQsUh37Xdpv5WN08xODBknd51Az4Kc/C91XvHbD9WdD2UKRPzWJDcZOtAfWIL5nyQsKJqNn5DM9L0QkUzvfAPEI8k+071g
o77Q03fdsP3R8kfK909zcIRYXPq7bH8Mab5nQlK8TnVUWDY/wuoxnH2hDlr9y8OFwuc/rc9ZPRVX8UU/HOzZSfO/R0ic9ez4ujw5weOL845Mt1sj3HhoQq5o2m1IMOkWuOez0yj+15LSgOH8d4bEmMRFqYTgKpLpDtNiXphZqVpwku+Dl1gL+bZ8PnijQ3pQiQhpuVzRTS776wOvOxl6btD1+aTj96Lc+m+d+7Z+35By6MuzG6M9466fPb1HUPhDhiI3Sa7psjfeqie2IM1ZqbsS5FEwgsbMuVqDpng5yonn92E09s0X443qbYdY3vtehgu3OSr8XTZwyUqOlz1BI+lB+nFnFeFr7jEUh/oFSIJoF
1IKEX2p1/aulqCjRVgeeCDEI00vpK7Cch7TgFRu2cAsP9Yl+jzYmjXzejXVAZisa+DTbWwQUcgnV9WS5OshUJSyuJ0+d4IZyD6g0rc7ZFYSxsoV1yHgrl2GRfzzZfUNYr/sB9m9e/6fbp4IMXjzbLWkU48nGUdIivOj0s33n7Yu+NNy4OP3TxcOvPyF9Wjvc9t9qUsB++/97NHWdoMUaiUs2zc5fvbUq/ZOw2FmEGB1dmHp2xch2diWqUQS2IBJ0Z/jOVJEIaYOLZlyJOAMGZ5cRdk3neunWD1kYxpqrnysLr95xJ+1+8mjdLuZ2NMUyvPzfsnt9My0gLprnQJGxHrscfSFBxCaLApi0hRLhI2XxA
pBEClvkeY8ImDLb0EurU7LjXiiRDdMQFx3o/R43DWZ2/zfIyodw3Ru3BFczUmsr9YVlOWJzMKR6U0yVLWndoqJ4c1lhsfYKgMoFnSaFk2sfIlSCgfDEfnssRUcyTrsRcMXlDOU5qB3vbvIQ5+TGFhJC5TAKdg3yBfCBkZrt5M4LjQIwpyshloKmxvA176jrh6yJoQqPb7Uj5B1FyvWpmsNu3h9WPvG5z50dKpvruNL50UNNythZRbr+h+L+ihda/5VXre8/v5+F3nls1Dvz3P7fajGE/vPv+zZ3MFTfbTOumxpe43FVfDNZvwWlZTRNsFZYoC1k0J8RrwTtkaP0QOlyCjQ/gDzMzVlD+g3aD8QoHH
HEjk4xNca2e0M4b8oRIuMBMto1Cw7wkaHl+o1S6aB3kgcaFx9LQICFCzi6HoMQ28SzcgWSY0SfaWFg6FOWmizNqVEQCIWXk2C4FatIhyJ9mbfcOev+GFnHN423Lh6IxrlUPmDIpmuDoTEtICQSL6M7hg5abQV8m7SBn1aNUDQsquqUxIOCWIJ+XXUe+ysbvmi0NAz4pF3zSoRwbJnaq04DH6H49fE/u823MfP7IOXwcke77inYlqyXmDxp0/1gobdvun2tKr/wlPmoNeQXbckyiZ50LaS+za4nh+u3M0fg7bxhWr7rBpeqKRhLS+t33FR/X/iywuCkFgaW4L9/32o1rZpNzjpY7T5vQtPu2fFoRLs
Y1FsZufQ+U8ctJfJx579eEXnBhnFObp8Z+rBhDQ8T4rIXubG+8pmQKEYInOjqq4RQAQ3WYy97fEJ0RUGEAbeyd4hhn9kVwWkLnP6kmZHLNKkS5EnyvSpjeYJIQWpPIR9o/MCrsr22QL33mMeQ1j/BzweSe54XmCqs/zKyU7tp5J/K2agrmcGIEFVzCctAHTnSjF6vl5esGAwmmldbRynDac8VdGyKvXDHvWKRjy6tTMK+0gL5BfpRiYXOGqCM/g1MoLKk0eXJqE70MLh9EvPhkpvdnGg8s6E6cSqCZ9SYpx4gBolA4EaVoHJlNeAxwQzH0W3fKiagdQEGWeCIm+1v3bV77jltrgicfv1cTTI/tpA2
t6ERLS0qibtDqYegaffFlXzr4yPWKDfrAkEcyh8CgVTuGJkeMxs9yz9pxbIWDdtlS6BwBi+1RaYuAg2+YgmeLokbeRCH62Fg7cF4TcwV1xBG94rkLLZz3ttHekNz+yPfQPgECR3BvftNKXCvjooXuCDE3eUJZWsEtLeqmuW8Ug8CUaUwmSmgOPmbNYsGBIscp+uJnCVrXjhWRvpkxgFBkMdhSmmARQ0JV5nhnn9gEetSF3ZHmAW4OEfed4b0lxwvt83JB5ApApFybO6CxzPSWGO6BhcGEvRXUJMe+muEqqVAvjYtkniQpgIATvbPW9nLzc56nfr8Dnryurle7CFQhe+xeekLyXBOuZ79IIGHACYGR
pD9n0Bemffd9mzu9APvBV69dZ83am4ym8R35SYu8HG3gGajPjxLbaJ33rU4rJWeyExjRMsYGvhV6uxZPsOORRQxJuFiDo5mKDZQOlFzcJPMhq50QbyYzCn0WQkDICYKpcZK+UT+HTDTOkzhKYfRiYXEKVJgPL7ZrTSmQr6gQDAxF1EQ8Q9OH4MIQRpQyTCMg4Vy2oANMWy2zYvtu0gRD+xNYsrzHbBnlNZ+L3AgC/yv9m0tLTV7vvSoc7DmqfKNmoe1RSjSnwsLrd02a7WpJrbp8zzCR8U4Uo+dOYDBPludBwfnGK1biwcxFpGcY/dXm2T4blGwtQNqwiBhxmQWQlYbEeL4V+tHNYGOm8p7JobNJt
UxloHnCWApDcNkQGfLwHCu8hLX2YBqeCNAFlWklFqpCErec/sH7N3e++7Zxbz0F+dHXrF37pjvWdqMJT78NaRJgUjXlzN62yhhzqZy6qWrixafaF18C4Z0Fswy+OcAx2x1fmYjRYfjFaJyNsNy5yg5zr2PUvwTmZCJElykXyuaBSopIi1pEuL+EskVaBeY+vibdQLApL0VTjW66w5475fb5vA8km52B0ldY+LKTmMeFkaGd69JbWCkGGlgNUJlfhYT7/BZWHKyseFncMmcv8EnXoo+8FRt+E+r/pMSVSFlCscKM51I5MbpS6VaFCARN9sCKRHLIA+U0ycCU4hTU3BQHLjK1ciRwqgkFSsyXZmW2SS
Env9lKJnn6kgCR2vxHAlU6b1bD3svfNMjhmNb1CFPC0oLjTlB25HaJmVaUrnfWpdY8bcam96+U42++dmPnXa8NO9xC08DU3qj+gKDQGcIB/gK0C4SB9VhqUgryt1LSevWUFIga3YSkZkc8vthi0648sPQO+uBIN3WE5fOgWphMvUDBiMhJlF9m6Q2UhDNSFdpRc308AuuF8TCukSKavEU+TKgOogmb7BnCtzfnCHVBeOKckBsgwhLoFnWzssB3RlfcbwE6xRpE6i+YKzn98nw0dGzCT6PY2KmdI5i+C7x3Vcg9Y+fcSoag0r5EmHUzvUFwZZSvKX2ZMoJLNbVn7ldtPYJXmaLlqLTqu5v7+Edx84g
VXlAXUKa8MPNtK13nFuSZgDL6oYIJ9N1uAS9izrnstHTo3dxUyueJB7Spx00pFIn8OSAQc0i3CMkIi9ET8m1idKdcYJRH9wlJ4NShDz8nhgwTaYnMEroLtw7JCQKCq5yDmYQFqqnTOuinm5ROSLYlFtauBTJFaGzgF7B9C/FsRkZkapnwMzQmZlK21WqJyNxssPGlLegNbQg5WlfZiZs1O46GmemQ0CIQIzLxPmIuYE4O5KSPtF1bztIoJTZjAn3mdkQXiMeuC2zGk1kbo2/wAEEdSJBD8eZApXLouZkZW1H77HeCoBIPpkSbN/dJRuoDW0D4BNMRNMqVMM1/q4KklLhBcqn5tVx42q7X4NOM59uz
vT+WXNsFikItkkgrKrB3ZUsP0r3b4NsJ5YMw9uwTTa5c5ja5L9jRqQlY7RumfuxC7fPBOwixWSP+MvMlRWqkOThb3xZEp6eHkd+HkUEghumjcI1TFgPVcZWZhDQoE0l+8/GAgak0biDkhXSJoBnEnHfjBFJbo76J+QdGmeRgbjRMgNLrggkpemY9UjTqnJAwIWLnBb/BGXp+DQst2jRWTbio90MPIrDhkTEe4+DMLqETWoaKyd/H6VWZlgX1PsFqMvqA0jMEAQNxhNts90+3+HzUwWmTRok+wVQNo0XyH3r00FIlBlpYbjziiqGuswvO3KL5/xAoSAAF/eSu0mmkPobOHAPLTXSv1qAXvgYoBCiLu
288ZEIm1sKCCmW5HBGPV7K0Jk/zCZrdHtmvzdsk4p3ceP3DysSAWqewYpdmQfqj0ja9Ax9OrKS6kvYiPuCXcicobZdOFE9LQZqcH3sfhJFg5x9HeLGrysqRuUQM0mtiE05kxrCpFsw/EH3Cg0cOSEMKdi7BZKlmtAqwXjVAHCZDYOmORpHMOXMGk5loL6ump413pE1R+lzISIILY55ZwBNqDqEV3JNFh2NTi1xoiRVy64hJQ+h8V2g27zrOB66dMuc/VfMKjuNSF0035OUQNpUWRqhfLICTOtPNbmOThzdd0S5ibiwaq1VFBqzNVMsgax4fTF4VltZ3ElZCjn3lnVoVdaSqK3g38rmiRvOInvBb4w
AfoBBVv2R7r+aCeeJw4yaJxjKx2QtAq6/SO3i8peEL9f92KKxVCoHKooEYzIqgzkf6ncFDYsRHzxfyc03t4y2aDVN+xWWgAwmwRNnbnMVdIbD4TsNtxJF61HpQ4RfhEKoKKyMsg4y0RyA7baFzJkZwwf0SgZiUTY9C/EPDeZq7pJMVmhrn8diOIMEW29azvOYMghK7HpkaNB+HC3bUigo0prDn+6oXEIZfxp90HKajCrL12ccXY5JpAatW/TAkA4t4pSW1yVSztI4G3psDVgvcEXHNQko339VxVeFOlNqgDI+UWf/oP7Pmz76cRPtTCZsWe2MJlqE7impi4KXmkdmyoZWXEJeSsZuIAVes9cXuP6b
QRTeORZUIBL8sUmhKN6rCRd2rYJUeur4Lypbr0jWwsflag/u/mnOOvn19oo5iQyBAevU1fi/SPlwIKS2TlYQ+GwYkC4MVajBWIOQr6J/TaRMJDr5SB745yldr99MoimKpA5irudhJ2GATgKjSTMjZl2OoTwM8xBqvqdKJhgoxC6MtIXrla51BjzthqTPN2sToDlTLRgYRICJfozbeWQgyqeZMrX+keUZOwO12U0k3wmTTgxmwK6NrX5L6sBg5Rh4jcWQgNK4YazapWcPzOBO9NKiDw9AsDKxcEPxyyA2FZqXVEonULhytOkXNWrtAZq9F4xo94jtZ8CJqtCtFChw4yrJopQl5WkNE5mVdT5pdoInQ
4m8kWYvvEk9CdK4m2fgkba5aBsG8TUSrYEQOCoQmoVmReOcKMG2hS3xCFXBm+kayt6qSwdh55ntfsJACG2RxgJYj3iGtANXKyDYPXRVXmNg81jxG0YUUeLX6umn5ntPrMSe9qEfBVjNUxSImZPTT2Pi3IAy6yGKg3wCKu1A5N7qZXhZCiFal6MwNRMCaQsjc7NGaEQTb6BTZg5Oy15Ew7TmLGZpwQq4MRWywfTsbAVYrwpICM5GAEih9g7M/Wlt9dHiHFSzn4X7gPW0fXBBlYa3u44OgC6NTNhuZmBv01ZryzUp/u8f8iK4gGse9uBTNwukl2FPR1zpJQD6Q2FjAhPcKCS7g7BpyU7BgMvVPs2Aoo
nM9NN/d1zX/nQiN8n6TgYQSKxrbt5By5hRhhB5hsJ/XsvfFx5V9BOyvAx90CqcBEGLmprkGrF3sKxQVXJyvmSJtdJGFNtUB/WB1A1VmJeQVotMeAimmTLP3T8jiwPOEXBzigtN4MWpQZDVvR+uBq3KMtkN2ZyKy4BqxpsjhrqU7eM0nr+Ko2qI6n7Xzs0YoMJA80I1druYqMywJKYHmyS2EFQg/9rP0CA7nQR+YEBswVTJJw6dCZq8PYqQxMR1Ql0awoKD996Izh4ChwUBFswKZsu/GTc5WiXA6C2l3q6llY3kCAi69OcoVWU8k5IWqWsKM6vOSeD5sTZo+VRcoN45rR9ViazQdNWkNdCiuCf0QDV
TQrkCaNxCxOBnOUOVeIRrATtmDricsKQy8b2jSmeHlMQkbJZOQYpSVaC0o8qN4ba4KOiMiKkclQoIM9boCCR3YjzZvYn5Rc4kEV2S+o4+Xmzb0vaIcqlWmdcVKo9j5SBhoiOeJ4beZjqZsuxOdZAJGykgw8iD5IdY2BwjweTolmgKTSHtdaNRWILhYkcL/Z+9SecQ+r7mS6gkRx8ZMkexoAf4aaIEVefpBtBiEFUlDTGAm5CQUvuWDkwUZgcGkRpkU8o8JtDeSUEERscf8uAO+NyquFqrDXjy1w5yYbmZIi2ZKzpSZnzZdwSC3R9qqvwLNIfhuDUS0Bxi6T47EQvjlpFtC5SYdoRbRJzpL4Xgkjgi
zMcWtWkAbTa7jmoOWvtBnZmdSzL6ZdMTEcLkwauEqINDe8JMA1SharcJIIvfJWNTW9RH6A8qLwXaSFqAL9shGDVBxRY4grUmH7cjKoOQEFB7MZRDpTqAZHNMJ1VnZ9AcCKz8tpyqsCVUZMMD8RGnzHtlEC/xuEqxGM9L6hSFshCLcGny3ZUNCS4UQSeSIZDALI9p4RkrCjdHNVGqgoImGeINn90dKdM+0J6X+bjQTX/evfqeUmtnmnK5mMw4yH4tAu2Gs0HShUBPoKLQVHw0ODyRBscmm6EAYLM814lgE0VIXHU/kcMCOEv37JtqxhmG4ULSTHYKo+sm+CTxvflbvZyPoz4mgHJmVrj6+LWglFMTv
xH0Dfec8oIkEOreJSV80SQAAAKlJREFUc/FYY/YH1+tvShaHdtwgWLSmv7Udc9OFwG2+eA+61fF3NUuRuqTM+j7MOSe9ds/CNa0gP1b259j8HCvt9GWu4+csiZ6wg1am6xYnKLy+0gG3Ee/la5q5i04ToA8++gX3oLfGpULtQxtOGmv8VvqItI9CNzwu87NMSPvvRpe8q3W3HSKuW/j62RnpIQJtZjvxDfeLxw4IF0rDr6sRXDbP5/dLkP8DT4/NkTO+vPkAAAAASUVORK5CYII="
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap13 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap13.BeginInit()
$bitmap13.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64l)
$bitmap13.EndInit()
# Freeze() prevents memory leaks.
$bitmap13.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.



#SendActive B64
$base64m = "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"
# Create a streaming image by streaming the base64 string to a bitmap streamsource
$bitmap14 = New-Object System.Windows.Media.Imaging.BitmapImage
$bitmap14.BeginInit()
$bitmap14.StreamSource = [System.IO.MemoryStream][System.Convert]::FromBase64String($base64m)
$bitmap14.EndInit()
# Freeze() prevents memory leaks.
$bitmap14.Freeze()
# Set source here. Take note in the XAML as to where the variable name was taken.


# ===========================================









$syncHash.button1.Add_Click({ 
 $log1 = "`n Running, This may take a while..."
$SyncHash.log_txt.AppendText($log1)


$syncHash.Userinput.IsEnabled = $True

        #region Boe's Additions
        $newRunspace =[runspacefactory]::CreateRunspace()
        $newRunspace.ApartmentState = "STA"
        $newRunspace.ThreadOptions = "ReuseThread"          
        $newRunspace.Open()
        $newRunspace.SessionStateProxy.SetVariable("SyncHash",$SyncHash) 
        $PowerShell = [PowerShell]::Create().AddScript({
Function Update-Window {
        Param (
            $Control,
            $Property,
            $Value,
            [switch]$AppendContent
        )

        # This is kind of a hack, there may be a better way to do this
        If ($Property -eq "Close") {
            $syncHash.Window.Dispatcher.invoke([action]{$syncHash.Window.Close()},"Normal")
            Return
        }

        # This updates the control based on the parameters passed to the function
        $syncHash.$Control.Dispatcher.Invoke([action]{
            # This bit is only really meaningful for the TextBox control, which might be useful for logging progress steps
            If ($PSBoundParameters['AppendContent']) {
                $syncHash.$Control.AppendText($Value)
            } Else {
                $syncHash.$Control.$Property,$Userinput = $Value
            }
        }, "Normal")
    }  
		
        

update-window -Control ProgressBar -Property Value -Value 25
 
       
        #Step the progress bar
      
      # Check if DNS Filter is installed and what version
$query = Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* | select DisplayName,DisplayVersion | where {$_.DisplayName -like "*DNS*"} | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

if ($query)
{
Write-Host "DNSFilter is installed with the version $query.DisplayVersion .."
}
else
{
Write-Host "DNSFilter is not installed" 
}

#Requires -RunAsAdministrator

# Get the Hyper-V feature and store it in $hyperv
$hyperv = Get-WindowsOptionalFeature -FeatureName Microsoft-Hyper-V-All -Online 

# Check if Hyper-V is already enabled.
if ($hyperv.State -eq "Enabled") {
    Write-Host "Hyper-V is already enabled." | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
} else {
    Write-Host "Hyper-V is disabled."
}



        
        #Step the progress bar
        update-window -Control ProgressBar -Property Value -Value 50
      
$site1 = "103.247.36.36"
$site2 = "103.247.37.37"
$time = Get-Date -Format d | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

     Test-Connection -ComputerName $site1 -Count 1 -ErrorAction SilentlyContinue | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
     Test-Connection -ComputerName $site2 -Count 1 -ErrorAction SilentlyContinue | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

     
     #check if Service is on related to DNS and DNS Filter

Get-Service "DNS*" | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
# Check device net configuration
ipconfig /all | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
# ping google 4 times
ping -n 4 8.8.8.8 | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

#Query original DNS address and run NSLOOKUP

if ($query){
$key = "HKLM:\SOFTWARE\DNSAgent\Agent"
}
else
{
$key = "HKLM:\SOFTWARE\DNSFilter\Agent"
}
Get-Item $key | % {
  $B64 = (Get-ItemProperty -Path $key -Name CurrentValues).CurrentValues
  $DecodedString=[System.Text.Encoding]::ASCII.GetString([System.Convert]::FromBase64String($B64))
} 
write-host "Encoded String:" $DecodedString

$DecodedString  -match '(?:\d{1,3}\.){3}\d{1,3}'
$Matches.Values | Sort-Object -Descending | Select-Object -Last 1

$OIP = $Matches.Values


nslookup -type=txt debug.dnsfilter.com $OIP | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
#NSLOOKUP with port 5353
nslookup -port=5353 -type=txt debug.dnsfilter.com $OIP | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

 
        
        #Step the progress bar
        update-window -Control ProgressBar -Property Value -Value 75
        #NSLOOKUP Against local AD Domain
$domain = (gwmi WIN32_ComputerSystem).Domain 
$var = Resolve-DnsName $domain ; $var.IPAddress
$ips = $var.IPAddress
foreach ($ip in $ips) {
nslookup -type=txt debug.dnsfilter.com $ip | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
}
 

 

Resolve-DnsName  debug.dnsfilter.com -Type txt | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
#netstat query
netstat -an | findstr 53 | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append


# Check public facing IP using ifconfig API
$uri = "https://ifconfig.co/json"

try
{
    $W = Invoke-WebRequest -Uri $uri -Headers $Content -Method Get
    $Wresult = ConvertFrom-Json -InputObject $W.Content
}
catch
{
    throw $_
}

$Wresult  -match '(?:\d{1,3}\.){3}\d{1,3}'
$Matches.Values 

$WAN = $Matches.Values
Select -First 1

write-output "Public Facing IP is:" $WAN| out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append

#Default gateway NSLOOKUP

$NextHop = Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select-Object -ExpandProperty NextHop

nslookup -type=txt debug.dnsfilter.com $NextHop | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append
# DNS leak test using ipleak.net API
$S = -join ((65..90) + (97..122) | Get-Random -Count 40 | % {[char]$_})
Set-Variable -Name "variable" -Value $S
# Build the URI (Universal Resource Identifier), also known as the Resource or Endpoint
$uri = "https://$variable.ipleak.net/json/"
# Submit the request to the RESTful Resource using the GET method
try
{
    $r = Invoke-WebRequest -Uri $uri -Headers $global -Method Get
    $result = ConvertFrom-Json -InputObject $r.Content
}
catch
{
    throw $_
}
Write-host $S
#Output result and format
$result | Select-Object -Property country_code,country_name,region_code,region_name,continent_code,continent_name,city_name,postal_code,postal_confidence,latitude,longitude,accuracy_radius,time_zone,metro_code,level,cache,myip,ip,reverse,tor,query_text,query_type,query_date |
 Format-Custom country_code,country_name,region_code,region_name,continent_code,continent_name,city_name,postal_code,postal_confidence,latitude,longitude,accuracy_radius,time_zone,metro_code,level,cache,myip,ip,reverse,tor,query_text,query_type,query_date
 $part1= $result | Select-Object -index 1,2
$part2= $result | Select-Object -last 2

write-output  "..............................................." | out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append
write-output "DNSLeak.net results:" $part1 `n $part2 | out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append
write-output  "..............................................." | out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append
write-output "Unique string:" $S | out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append
write-output  "..............................................." | out-file c:\temp\debugfile.txt -Encoding "UTF8" -Append
$content = Get-Content c:\temp\debugfile.txt
$content | Foreach {$_.Trim()} | Set-Content c:\temp\debugfile.txt


        #Step the progress bar

        update-window -Control ProgressBar -Property Value -Value 100
        update-window -Control Userinput -property Value -value $False -IsEnabled

         $log = "`n Done!"
$syncHash.log_txt.Dispatcher.Invoke([action]{$syncHash.log_txt.Text=$syncHash.log_txt.AppendText($log)}, "Normal") 


     
 
        

        })
                
$syncHash.Window.Add_Closed({
        Write-Verbose 'Halt runspace cleanup job processing'
        $jobCleanup.Flag = $True

        #Stop all runspaces
        $jobCleanup.PowerShell.Dispose()    
        [System.GC]::Collect()  

    })
    $RunspacePool.Close()
    #endregion Window Close 
    #endregion Boe's Additions

    #$x.Host.Runspace.Events.GenerateEvent( "TestClicked", $x.test, $null, "test event")

    #$syncHash.Window.Activate()
     $Script:JobCleanup = [hashtable]::Synchronized(@{})
    $Script:Jobs = [system.collections.arraylist]::Synchronized((New-Object System.Collections.ArrayList))



        $PowerShell.Runspace = $newRunspace
        [void]$Jobs.Add((
            [pscustomobject]@{
                PowerShell = $PowerShell
                Runspace = $PowerShell.BeginInvoke()
            }
        ))
        
    })



    $syncHash.button6.Add_Click({
	  $wshell = New-Object -ComObject Wscript.Shell
$Output = $wshell.Popup("Roaming Client Debugging mode will be turned off upon exit of DNS Clarity!",0,"Roaming Client Reminder",0)
    $syncHash.form.Close()


    if ($con = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config") {
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"}
 
 else { ($con = Get-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config") 
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config"
}

    Restart-Service -Name "DNSFilter Agent"
    Restart-Service -Name "DNS Agent"

    Stop-Process -Name "DNS Clarity"


})

$form.Add_Closed({
    
})
$syncHash.form.Add_Closed({
    
})

    $syncHash.button2.Add_Click({ Invoke-Item "C:\temp\debugfile.txt"}) | Out-Null

 
    
    $syncHash.button3.Add_Click({
         
         $syncHash.Notes.Text | Out-File -FilePath c:\temp\debugfile.txt -Encoding "UTF8" -Append

})
       
    function IsThereText {
	if ($syncHash.Userinput.Text.Length -gt 8)
	{
		$syncHash.button3.IsEnabled = $True
        $syncHash.Notes.IsEnabled = $True
        $syncHash.button3.Opacity ="1"
	}
	else
	{
		$syncHash.button3.IsEnabled = $False
        $syncHash.Notes.IsEnabled = $False
        $syncHash.button3.Opacity =".3"
	}
    
}
    if ($syncHash.Userinput.Add_TextChanged({IsThereText}) -eq $True) {
    WPFbutton3.IsEnabled = $True
    $syncHash.button3.Opacity ="1"
    }
    else
    {
    $syncHash.button3.IsEnabled = $False
    $syncHash.button3.Opacity =".3"
    }


    $syncHash.Userinput.Add_GotFocus({
    if ($syncHash.Userinput.Text -eq 'Type valid Email') {
        $syncHash.Userinput.Foreground = 'Black'
        $syncHash.Userinput.Background = "#FF4A6681"
        $syncHash.Userinput.Text = ''
    }
})

    $syncHash.Userinput.Add_LostFocus({
    if ($syncHash.Userinput.Text -eq '') {
        $syncHash.Userinput.Text = 'Type valid Email'
        $syncHash.Userinput.Foreground = 'Black'
        $syncHash.Userinput.Background = "#FF4B6883"
    }
})

    $syncHash.Notes.Add_GotFocus({
    if ($syncHash.Notes.Text -eq 'Notes and Comments') {
        $syncHash.Notes.Foreground = 'Black'
        $syncHash.Notes.Background = "#FF4A6681"
        $syncHash.Notes.Text = ''
    }
})

    $syncHash.Notes.Add_LostFocus({
    if ($syncHash.Notes.Text -eq '') {
        $syncHash.Notes.Text = 'Notes and Comments'
        $syncHash.Notes.Foreground = 'Black'
        $syncHash.Notes.Background = "#FF4B6883"
    }
})


$syncHash.button3.Add_Click({ 
$ClientEmail = $syncHash.Userinput.Text

$FilePath = 'c:\temp\debugfile.txt';
$URL = 'https://hooks.zapier.com/hooks/catch/1363501/ot1k50p/';

$fileBytes = [System.IO.File]::ReadAllBytes($FilePath);
$fileEnc = [System.Text.Encoding]::GetEncoding('UTF-8').GetString($fileBytes);
$boundary = [System.Guid]::NewGuid().ToString(); 
$LF = "`r`n";

$bodyLines = ( 
    "--$boundary",
    "Content-Disposition: form-data; name=`"file`"; filename=`"c:\temp\debugfile.txt`"",
    "Content-Type: application/octet-stream$LF",
    $fileEnc,
    "--$boundary--$LF" 
) -join $LF
$apikey = "rKqlgfhDcuYOzXZUJsMwAPyoQmIvEBHFWbdTGNxV"
$email = "$ClientEmail"
Invoke-RestMethod -Uri $URL -Method Post -ContentType "multipart/form-data; boundary=`"$boundary`"" -Body $bodyLines -Header @{ 
    "X-API-Key" = $apiKey
    "X-Customer-Email" = $email
}

         $log5 = "`n Sent!"
$syncHash.log_txt.Dispatcher.Invoke([action]{$syncHash.log_txt.Text=$syncHash.log_txt.AppendText($log5)}, "Normal") 

}) | Out-Null


$imagex = New-Object System.Windows.Controls.Image
$imagex.Source = "C:\Program Files (x86)\DNS Clarity\RCNote.png"
$syncHash.RCNote.Content = $imagex


#debug images
$image1 = New-Object System.Windows.Controls.Image
$image1.Source = $bitmap10
$image4 = New-Object System.Windows.Controls.Image
$image4.Source = $bitmap8
$image2 = New-Object System.Windows.Controls.Image
$image2.Source = $bitmap9
$image3 = New-Object System.Windows.Controls.Image
$image3.Source = $bitmap7

#Active images
$image5 = New-Object System.Windows.Controls.Image
$image5.Source = $bitmap4
$image6 = New-Object System.Windows.Controls.Image
$image6.Source = $bitmap5
$image7 = New-Object System.Windows.Controls.Image
$image7.Source = $bitmap6
$image8 = New-Object System.Windows.Controls.Image
$image8.Source = $bitmap12
$image9 = New-Object System.Windows.Controls.Image
$image9.Source = $bitmap13
$image10 = New-Object System.Windows.Controls.Image
$image10.Source = $bitmap14




$syncHash.button1.add_MouseEnter({
$syncHash.button1.Content = $image8 
})
$syncHash.button1.Add_MouseLeave({
$syncHash.button1.Content = $image5
})


$syncHash.button2.add_MouseEnter({
$syncHash.button2.Content = $image9
})
$syncHash.button2.Add_MouseLeave({
$syncHash.button2.Content = $image6
})

$syncHash.button3.add_MouseEnter({
$syncHash.button3.Content = $image10
})
$syncHash.button3.Add_MouseLeave({
$syncHash.button3.Content = $image7
})


$file = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config" 
$containsWord = $file | %{$_ -match "INFO"}
if ($containsWord -contains $true) {
   $syncHash.button5.IsEnabled = $False
   $syncHash.button5.Content = $image1      
        $syncHash.button5.Background = "Transparent"}


$image2 = New-Object System.Windows.Controls.Image
$image2.Source = $bitmap9

$file = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config" 
$containsWord = $file | %{$_ -match "DEBUG"}
if ($containsWord -contains $true) {
   $syncHash.button4.IsEnabled = $False
   $syncHash.button4.Content = $image2      
        $syncHash.button4.Background = "Transparent"
$syncHash.button5.Content = $image4}


# Enabled debug mode in Roaming client
$syncHash.button4.Add_Click({ 
if ($con = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config") {
$con | % { $_.Replace("INFO", "DEBUG") } | Set-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"}
 
 else { ($con = Get-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config") 
$con | % { $_.Replace("INFO", "DEBUG") } | Set-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config"
}


[xml]$myXML = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"
$myXML.configuration.log4net.appender.file.value = "C:/temp/RCLog.txt"
$myXML.Save("C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config")

[xml]$myXML = Get-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config"
$myXML.configuration.log4net.appender.file.value = "C:/temp/RCLog.txt"
$myXML.Save("C:\Program Files\DNS Agent\DNS Agent.exe.config")


   $syncHash.button5.IsEnabled = $True
   $syncHash.button4.IsEnabled = $False
   $syncHash.button4.Content = $image2  
   $syncHash.button5.Content = $image4     
        $syncHash.button5.Background = "Transparent"
        

}) | Out-Null


$image = New-Object System.Windows.Controls.Image
$image.Source = "C:\Program Files (x86)\DNS Clarity\UpdatedDisableSelect.png"


$syncHash.button5.Add_Click({ 
if ($con = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config") {
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"}
 
 else { ($con = Get-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config") 
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config"
}


[xml]$myXML = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"
$myXML.configuration.log4net.appender.file.value = "C:/temp/RCLog.txt"
$myXML.Save("C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config")

[xml]$myXML = Get-Content "C:\Program Files\DNS Agent\DNS Agent.exe.config"
$myXML.configuration.log4net.appender.file.value = "C:/temp/RCLog.txt"
$myXML.Save("C:\Program Files\DNS Agent\DNS Agent.exe.config")



 $syncHash.button4.IsEnabled = $True
   $syncHash.button5.IsEnabled = $False
    $syncHash.button5.Content = $image
    $syncHash.button4.Content = $image3    
        $syncHash.button4.Background = "Transparent"


}) | Out-Null


Register-EngineEvent PowerShell.Exiting –Action { 
Stop-Process -Name "synchash"
}
Register-EngineEvent PowerShell.Exiting –Action { 


if ($con = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config") {
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"}
 
 else { ($con = Get-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config") 
$con | % { $_.Replace("DEBUG", "INFO") } | Set-Content "C:\Program Files\DNSFilter Agent\DNSFilter Agent.exe.config"
}

 }

 $syncHash.button4.IsEnabled = $True
 $syncHash.button5.IsEnabled = $False
        
        $syncHash.button5.Background = "Transparent"


$query = Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* | select DisplayName,DisplayVersion | where {$_.DisplayName -like "*DNS*"} 
if ($query)
{
$syncHash.button5.IsEnabled = $True
$syncHash.button4.IsEnabled = $True
$syncHash.button5.Visibility = 'Visible'
$syncHash.button4.Visibility = 'Visible'
$syncHash.RCNote.Visibility = 'Visible'
}
else
{ 
$syncHash.button5.IsEnabled = $False
$syncHash.button4.IsEnabled = $False
$syncHash.button5.Content = $image4
$syncHash.button4.Content = $image3
$syncHash.button5.Opacity = '.5'
$syncHash.button4.Opacity = '.5'
$syncHash.RCNote.Opacity = '.5'
}

    #region Window Close 
    $syncHash.Window.Add_Closed({
        Write-Verbose 'Halt runspace cleanup job processing'
        $jobCleanup.Flag = $True

        #Stop all runspaces
        $jobCleanup.PowerShell.Dispose()      
    })
    $RunspacePool.Close()
    #endregion Window Close 
    

    #$x.Host.Runspace.Events.GenerateEvent( "TestClicked", $x.test, $null, "test event")

    #$syncHash.Window.Activate()
     $Script:JobCleanup = [hashtable]::Synchronized(@{})
    $Script:Jobs = [system.collections.arraylist]::Synchronized((New-Object System.Collections.ArrayList))

    #region Background runspace to clean up jobs
    $Window.Add_Closing({$_.Cancel = $true})
    $syncHash.Window.ShowDialog() | Out-Null
    $syncHash.Error = $Error
})

$psCmd.Runspace = $newRunspace
$data = $psCmd.BeginInvoke()

#Written by Jon Cohen, who still won't simply do it in C#
#Design by Jordan “I barely even know UI/UX” Dusek

