import React, { useState } from "react";
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  MenuItem,
  Alert,
  InputAdornment,
  IconButton,
  LinearProgress,
  Button,
} from "@mui/material";
import { LoadingButton } from "@mui/lab";
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { buildApiUrl } from "../config";

const plans = [
  { value: "pilot", label: "Pilot" },
  { value: "pro", label: "Pro" },
  { value: "enterprise", label: "Enterprise" },
];

// Helper: password validation
const isPasswordValid = (password: string) =>
  /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$/.test(password);

const API_URL = buildApiUrl("");

type FormState = {
  name: string;
  plan: string;
  root_user_name: string;
  root_user_email: string;
  root_user_password: string;
};

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>({
    name: "",
    plan: "",
    root_user_name: "",
    root_user_email: "",
    root_user_password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Basic validation
    if (
      !form.name ||
      !form.plan ||
      !form.root_user_name ||
      !form.root_user_email ||
      !form.root_user_password
    ) {
      setError("All fields are required.");
      return;
    }
    if (!isPasswordValid(form.root_user_password)) {
      setError(
        "Password must be at least 8 characters, include one letter, one number, and one symbol."
      );
      return;
    }

    setLoading(true);

    try {
      const res = await axios.post(`${API_URL}/api/v1/register-new-tenant`, {
        ...form,
        credit_balance: 0, // hidden; default
        settings: {}, // hidden; default
      });
      setSuccess(res.data);
    } catch (err: any) {
      let msg =
        err?.response?.data?.detail ||
        "Failed to register. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <Container maxWidth="sm">
        <Box mt={8}>
          <Card>
            <CardContent>
              <Typography variant="h5" gutterBottom>
                Tenant Registered!
              </Typography>
              <Typography>
                <b>Tenant:</b> {success.name}
              </Typography>
              <Typography>
                <b>Root User Email:</b> {success.root_user.email}
              </Typography>
              <Box mt={2}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={() => navigate("/login")}
                >
                  Go to Login
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="sm">
      <Box mt={8}>
        <Card>
          <CardContent>
            <Typography variant="h5" gutterBottom>
              Register Tenant (Pilot Demo)
            </Typography>
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
            <form onSubmit={handleSubmit} noValidate>
              <TextField
                fullWidth
                margin="normal"
                label="Tenant Name"
                name="name"
                value={form.name}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                select
                margin="normal"
                label="Plan"
                name="plan"
                value={form.plan}
                onChange={handleChange}
                required
              >
                {plans.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                fullWidth
                margin="normal"
                label="Root User Name"
                name="root_user_name"
                value={form.root_user_name}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Root User Email"
                name="root_user_email"
                type="email"
                value={form.root_user_email}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Root User Password"
                name="root_user_password"
                type={showPw ? 'text' : 'password'}
                value={form.root_user_password}
                onChange={handleChange}
                required
                helperText="Min. 8 characters, at least one letter, number, and symbol."
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton aria-label="toggle password visibility" onClick={() => setShowPw(v => !v)} edge="end">
                        {showPw ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />
              <Box mt={1}>
                <LinearProgress variant="determinate" value={Math.min(100, form.root_user_password.length * 10)} aria-label="password strength" />
              </Box>
              <Box mt={2}>
                <LoadingButton
                  variant="contained"
                  color="primary"
                  type="submit"
                  fullWidth
                  loading={loading}
                  loadingPosition="start"
                  size="large"
                >
                  Register Tenant
                </LoadingButton>
              </Box>
            </form>
          </CardContent>
        </Card>
        <Box mt={2} textAlign="center">
          <Button color="secondary" onClick={() => navigate("/login")}> 
            Already have an account? Login
          </Button>
        </Box>
      </Box>
    </Container>
  );
}
