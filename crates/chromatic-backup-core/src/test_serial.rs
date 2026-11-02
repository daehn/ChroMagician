//! PTYs transport real bytes but Darwin does not implement their baud ioctls.
//! Keep requested speeds in the test adapter; production USB ports are untouched.
use serialport::{ClearBuffer, DataBits, FlowControl, Parity, SerialPort, StopBits};
use std::io::{Read, Write};
use std::sync::{
    Arc,
    atomic::{AtomicU32, Ordering},
};
use std::time::Duration;

pub struct TestPort {
    inner: Box<dyn SerialPort>,
    baud: Arc<AtomicU32>,
}

pub fn pair() -> serialport::Result<(TestPort, TestPort)> {
    let (master, slave) = serialport::TTYPort::pair()?;
    let baud = Arc::new(AtomicU32::new(115_200));
    Ok((
        TestPort {
            inner: Box::new(slave),
            baud: baud.clone(),
        },
        TestPort {
            inner: Box::new(master),
            baud,
        },
    ))
}

impl Read for TestPort {
    fn read(&mut self, bytes: &mut [u8]) -> std::io::Result<usize> {
        self.inner.read(bytes)
    }
}
impl Write for TestPort {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.inner.write(bytes)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        self.inner.flush()
    }
}
impl SerialPort for TestPort {
    fn name(&self) -> Option<String> {
        self.inner.name()
    }
    fn baud_rate(&self) -> serialport::Result<u32> {
        Ok(self.baud.load(Ordering::SeqCst))
    }
    fn set_baud_rate(&mut self, baud: u32) -> serialport::Result<()> {
        #[cfg(not(target_os = "macos"))]
        self.inner.set_baud_rate(baud)?;
        self.baud.store(baud, Ordering::SeqCst);
        Ok(())
    }
    fn data_bits(&self) -> serialport::Result<DataBits> {
        self.inner.data_bits()
    }
    fn flow_control(&self) -> serialport::Result<FlowControl> {
        self.inner.flow_control()
    }
    fn parity(&self) -> serialport::Result<Parity> {
        self.inner.parity()
    }
    fn stop_bits(&self) -> serialport::Result<StopBits> {
        self.inner.stop_bits()
    }
    fn timeout(&self) -> Duration {
        self.inner.timeout()
    }
    fn set_data_bits(&mut self, value: DataBits) -> serialport::Result<()> {
        self.inner.set_data_bits(value)
    }
    fn set_flow_control(&mut self, value: FlowControl) -> serialport::Result<()> {
        self.inner.set_flow_control(value)
    }
    fn set_parity(&mut self, value: Parity) -> serialport::Result<()> {
        self.inner.set_parity(value)
    }
    fn set_stop_bits(&mut self, value: StopBits) -> serialport::Result<()> {
        self.inner.set_stop_bits(value)
    }
    fn set_timeout(&mut self, value: Duration) -> serialport::Result<()> {
        self.inner.set_timeout(value)
    }
    fn write_request_to_send(&mut self, value: bool) -> serialport::Result<()> {
        self.inner.write_request_to_send(value)
    }
    fn write_data_terminal_ready(&mut self, value: bool) -> serialport::Result<()> {
        self.inner.write_data_terminal_ready(value)
    }
    fn read_clear_to_send(&mut self) -> serialport::Result<bool> {
        self.inner.read_clear_to_send()
    }
    fn read_data_set_ready(&mut self) -> serialport::Result<bool> {
        self.inner.read_data_set_ready()
    }
    fn read_ring_indicator(&mut self) -> serialport::Result<bool> {
        self.inner.read_ring_indicator()
    }
    fn read_carrier_detect(&mut self) -> serialport::Result<bool> {
        self.inner.read_carrier_detect()
    }
    fn bytes_to_read(&self) -> serialport::Result<u32> {
        self.inner.bytes_to_read()
    }
    fn bytes_to_write(&self) -> serialport::Result<u32> {
        self.inner.bytes_to_write()
    }
    fn clear(&self, buffer: ClearBuffer) -> serialport::Result<()> {
        self.inner.clear(buffer)
    }
    fn try_clone(&self) -> serialport::Result<Box<dyn SerialPort>> {
        Ok(Box::new(Self {
            inner: self.inner.try_clone()?,
            baud: self.baud.clone(),
        }))
    }
    fn set_break(&self) -> serialport::Result<()> {
        self.inner.set_break()
    }
    fn clear_break(&self) -> serialport::Result<()> {
        self.inner.clear_break()
    }
}
