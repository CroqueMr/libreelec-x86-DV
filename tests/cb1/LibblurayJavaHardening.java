import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import org.dvb.dsmcc.DSMCCObject;
import org.dvb.dsmcc.NPTRate;
import org.dvb.dsmcc.NotLoadedException;
import org.dvb.event.EventManager;

public class LibblurayJavaHardening {
    public static class EventSubclass extends EventManager {}
    public static void main(String[] args) throws Exception {
        if (args[0].equals("unload")) {
            File file = File.createTempFile("bdj-unload", ".dat");
            try {
                DSMCCObject object = new DSMCCObject(file.getPath());
                boolean rejected = false;
                try { object.unload(); } catch (NotLoadedException expected) { rejected = true; }
                assert rejected;
                object.synchronousLoad();
                assert object.isLoaded();
                object.unload();
                assert !object.isLoaded();
                object.synchronousLoad();
                object.unload();
                assert !object.isLoaded();
            } finally { file.delete(); }
        } else if (args[0].equals("rate")) {
            Constructor<?> c = NPTRate.class.getDeclaredConstructor(int.class, int.class);
            assert !Modifier.isPublic(c.getModifiers());
            assert !Modifier.isPrivate(c.getModifiers());
            assert !Modifier.isProtected(c.getModifiers());
            c.setAccessible(true);
            NPTRate rate = (NPTRate)c.newInstance(3, 2);
            assert rate.getNumerator() == 3 && rate.getDenominator() == 2;
        } else {
            Constructor<?> c = EventManager.class.getDeclaredConstructor();
            assert Modifier.isProtected(c.getModifiers());
            assert new EventSubclass() != null;
            assert EventManager.getInstance() == EventManager.getInstance();
            EventManager previous = EventManager.getInstance();
            EventManager.shutdown();
            assert EventManager.getInstance() != previous;
        }
    }
}
