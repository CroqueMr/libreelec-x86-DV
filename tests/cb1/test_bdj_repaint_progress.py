"""Exercise the real BD-J refresh task with a deterministic monotonic clock."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BdjRepaintProgress(unittest.TestCase):
    def test_continuous_paint_cannot_starve_refresh_and_quiet_paint_stays_prompt(self):
        include = os.environ.get('LIBBLURAY_TEST_INCLUDE')
        java = os.environ.get('JAVA_HOME')
        if not include or not java:
            self.skipTest('Matched libbluray sources and JDK required')
        root = Path(__file__).resolve().parents[2]
        owner = 'src/libbluray/bdj/java/java/awt/BDRootWindow.java'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            target = folder / owner
            target.parent.mkdir(parents=True)
            shutil.copy2(Path(include).parent / owner, target)
            patch = root / 'packages/multimedia/libbluray/patches/0004-bdj-bounded-repaint-sync.patch'
            if patch.exists():
                result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                                        cwd=folder, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source = target.read_text()
            start = source.index('private static class RefreshTimerTask')
            brace = source.index('{', start)
            depth, end = 1, brace + 1
            while depth:
                depth += (source[end] == '{') - (source[end] == '}')
                end += 1
            task = source[start:end]
            fixture = '''
import java.util.TimerTask;
public class RepaintProgress {
    static class System {
        static long now;
        static long nanoTime() { return now; }
    }
    static class BDRootWindow {
        int changeCount, flushes;
        void sync() { flushes++; changeCount = 0; }
    }
    TASK
    static void require(boolean value, String why) {
        if (!value) throw new AssertionError(why);
    }
    public static void main(String[] args) {
        for (long origin : new long[] {0, -500000000L, Long.MAX_VALUE - 50000000L}) {
            System.now = origin;
            BDRootWindow window = new BDRootWindow();
            window.changeCount = 1;
            RefreshTimerTask task = new RefreshTimerTask(window);
            for (int tick = 1; tick <= 3; tick++) {
                window.changeCount++;
                System.now = origin + tick * 40000000L;
                task.run();
                require(window.flushes == (tick < 3 ? 0 : 1),
                        "continuous repaint must flush by the third 40ms tick");
            }
            // A new pending paint gets a new budget after the prior task ended.
            window.changeCount = 1;
            RefreshTimerTask next = new RefreshTimerTask(window);
            window.changeCount++;
            System.now += 40000000L;
            next.run();
            require(window.flushes == 1, "new paint must not inherit an expired budget");
            System.now += 40000000L;
            next.run();
            require(window.flushes == 2, "quiet paint must flush at the next normal tick");
        }
        BDRootWindow quiet = new BDRootWindow();
        quiet.changeCount = 1;
        RefreshTimerTask task = new RefreshTimerTask(quiet);
        System.now += 40000000L;
        task.run();
        require(quiet.flushes == 1, "unchanged paint should not wait for the bound");
    }
}
'''.replace('TASK', task)
            (folder / 'RepaintProgress.java').write_text(fixture)
            result = subprocess.run([str(Path(java) / 'bin/javac'), 'RepaintProgress.java'],
                                    cwd=folder, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(Path(java) / 'bin/java'), '-cp', str(folder),
                                     'RepaintProgress'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
