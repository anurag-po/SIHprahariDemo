using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace PrahariLauncher
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.Title = "PRAHARI — One-Click Launcher & Auto-Setup";
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("================================================================================");
            Console.WriteLine("                 🛰️  PRAHARI HAR ASSISTANT — FINAL RUN                         ");
            Console.WriteLine("================================================================================");
            Console.ResetColor();
            Console.WriteLine();

            // Locate project root directory
            string currentDir = AppDomain.CurrentDomain.BaseDirectory;
            string projectRoot = currentDir;

            if (File.Exists(Path.Combine(currentDir, "requirements.txt")) && Directory.Exists(Path.Combine(currentDir, "src")))
            {
                projectRoot = currentDir;
            }
            else if (Directory.Exists(Path.Combine(Directory.GetParent(currentDir).FullName, "src")))
            {
                projectRoot = Directory.GetParent(currentDir).FullName;
            }

            Console.WriteLine("[INFO] Project Root: " + projectRoot);

            // Step 1: Detect Python
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("\n[1/3] Locating Python environment...");
            Console.ResetColor();

            string pythonCmd = FindPython();
            if (string.IsNullOrEmpty(pythonCmd))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Python was not found on your system.");
                Console.WriteLine("Please install Python 3.10+ from https://www.python.org/downloads/");
                Console.WriteLine("Remember to check the box 'Add Python to PATH' during installation.");
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("[OK] Python Interpreter: " + pythonCmd);
            Console.ResetColor();

            // Step 2: Auto-verify & install dependencies
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("\n[2/3] Verifying and setting up required project dependencies...");
            Console.ResetColor();

            string reqPath = Path.Combine(projectRoot, "requirements.txt");
            if (!File.Exists(reqPath))
            {
                reqPath = Path.Combine(currentDir, "requirements.txt");
            }

            if (File.Exists(reqPath))
            {
                RunProcess(pythonCmd, "-m pip install -r \"" + reqPath + "\"", projectRoot);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("[OK] All project dependencies verified.");
                Console.ResetColor();
            }

            // Step 3: Check AI Models
            string downloadScript = Path.Combine(projectRoot, "src", "download_models.py");
            if (File.Exists(downloadScript))
            {
                RunProcess(pythonCmd, "\"" + downloadScript + "\"", projectRoot);
            }

            // Step 4: Launch PRAHARI
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("\n================================================================================");
            Console.WriteLine("[3/3] Launching PRAHARI Mission HAR Assistant...");
            Console.WriteLine("================================================================================");
            Console.ResetColor();
            Console.WriteLine();
            Console.WriteLine("Select video feed source:");
            Console.WriteLine("  [1] Android Phone Camera (No App / Chrome Browser Bridge) [Recommended]");
            Console.WriteLine("  [2] Laptop / USB Webcam");
            Console.WriteLine();
            Console.Write("Choice (1 or 2) [Default 1]: ");

            string choice = Console.ReadLine();
            if (string.IsNullOrWhiteSpace(choice)) choice = "1";

            string mainScript = Path.Combine(projectRoot, "src", "main.py");
            string configPath = Path.Combine(projectRoot, "config", "desk_objects_experiment.json");

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonCmd;
            psi.WorkingDirectory = projectRoot;
            psi.UseShellExecute = false;

            if (choice.Trim() == "2")
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n[STARTING] Launching PRAHARI with USB Camera index 0...");
                Console.ResetColor();
                psi.Arguments = "\"" + mainScript + "\" --config \"" + configPath + "\" --camera 0";
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("\n[STARTING] Launching PRAHARI with Mobile Phone Camera Bridge...");
                Console.ResetColor();
                psi.Arguments = "\"" + mainScript + "\" --config \"" + configPath + "\"";
                psi.EnvironmentVariables["PRAHARI_CAMERA_TYPE"] = "browser";
            }

            try
            {
                using (Process appProc = Process.Start(psi))
                {
                    appProc.WaitForExit();
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[ERROR] Failed to start application: " + ex.Message);
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
            }
        }

        static string FindPython()
        {
            string[] candidates = new string[] { "python", "py", "python3" };
            foreach (string candidate in candidates)
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo(candidate, "--version");
                    psi.RedirectStandardOutput = true;
                    psi.RedirectStandardError = true;
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    using (Process p = Process.Start(psi))
                    {
                        p.WaitForExit(3000);
                        if (p.ExitCode == 0) return candidate;
                    }
                }
                catch { }
            }

            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] searchPaths = new string[]
            {
                Path.Combine(localAppData, "Programs", "Python", "Python312", "python.exe"),
                Path.Combine(localAppData, "Programs", "Python", "Python311", "python.exe"),
                Path.Combine(localAppData, "Programs", "Python", "Python310", "python.exe"),
                @"C:\Python312\python.exe",
                @"C:\Python311\python.exe",
                @"C:\Python310\python.exe"
            };

            foreach (string path in searchPaths)
            {
                if (File.Exists(path)) return path;
            }

            return null;
        }

        static int RunProcess(string fileName, string args, string workingDir)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(fileName, args);
                psi.WorkingDirectory = workingDir;
                psi.UseShellExecute = false;
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("[ERROR] " + ex.Message);
                return -1;
            }
        }
    }
}
